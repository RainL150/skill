import { assertJsonWrite, authorize, publicError, readJson, sendJson } from "./http_helpers.mjs";
import { runPythonJson, streamPythonNdjson } from "./python_bridge.mjs";


function queryValue(url, key, fallback = "") {
  const value = url.searchParams.get(key);
  return value === null ? fallback : String(value).slice(0, 120);
}

function workerStatus(payload) {
  return Number(payload?.meta?.status) || (payload?.ok === false ? 500 : 200);
}

const READ_POLICIES = {
  portfolio: { freshMs: 30_000, staleMs: 30 * 60_000 },
  watchlist: { freshMs: 30_000, staleMs: 30 * 60_000 },
  daily: { freshMs: 5 * 60_000, staleMs: 30 * 60_000 },
  intel: { freshMs: 5 * 60_000, staleMs: 30 * 60_000 },
  stock: { freshMs: 60_000, staleMs: 30 * 60_000 },
  financials: { freshMs: 60 * 60_000, staleMs: 24 * 60 * 60_000 },
  capabilities: { freshMs: 5 * 60_000, staleMs: 24 * 60 * 60_000 },
};

function clonePayload(payload) {
  return JSON.parse(JSON.stringify(payload));
}

function markResponseCache(payload, ageMs, stale) {
  const cloned = clonePayload(payload);
  cloned.meta ||= {};
  const ageSeconds = Math.max(0, Math.round(ageMs / 100) / 10);
  const upstream = cloned.meta.cache || {};
  cloned.meta.response_cache = { hit: true, stale, age_seconds: ageSeconds, layer: "node-memory" };
  cloned.meta.cache = {
    ...upstream,
    hit: true,
    stale: Boolean(upstream.stale || stale),
    age_seconds: ageSeconds,
  };
  if (stale) {
    cloned.meta.warnings = [...new Set([
      ...(cloned.meta.warnings || []),
      `先显示 ${Math.round(ageSeconds)} 秒前快照，后台正在刷新`,
    ])];
  }
  return cloned;
}

export function createResponseCache({ now = () => Date.now() } = {}) {
  const entries = new Map();
  const inflight = new Map();

  const refresh = (key, loader) => {
    if (inflight.has(key)) return inflight.get(key);
    const pending = Promise.resolve()
      .then(loader)
      .then((payload) => {
        if (payload && payload.ok !== false) entries.set(key, { payload, createdAt: now() });
        return payload;
      })
      .finally(() => inflight.delete(key));
    inflight.set(key, pending);
    return pending;
  };

  return {
    async get(key, loader, policy, { force = false } = {}) {
      const hit = entries.get(key);
      const ageMs = hit ? Math.max(0, now() - hit.createdAt) : Infinity;
      if (!force && hit && ageMs <= policy.freshMs) {
        return markResponseCache(hit.payload, ageMs, false);
      }
      if (!force && hit && ageMs <= policy.staleMs) {
        void refresh(key, loader).catch(() => {});
        return markResponseCache(hit.payload, ageMs, true);
      }
      return refresh(key, loader);
    },
    clear(key) {
      if (key) entries.delete(key);
      else entries.clear();
    },
  };
}

export function createApiRouter(config) {
  const dataArgs = (command, extra = []) => [command, ...extra, "--workspace", config.workspace, "--json"];
  const runData = async (command, extra = [], body = "") => runPythonJson({
    python: config.python,
    script: config.dashboardDataScript,
    args: dataArgs(command, extra),
    input: body,
    timeoutMs: config.dataTimeoutMs,
  });
  const responseCache = createResponseCache();

  async function handle(req, res, url) {
    if (!url.pathname.startsWith("/api/")) return false;
    if (!authorize(req, config.apiKey)) {
      sendJson(res, {
        ok: false,
        data: null,
        meta: { status: 401, warnings: ["后端访问密钥无效"] },
        errors: [{ scope: "auth", provider: null, code: "UNAUTHORIZED", message: "未授权", retryable: false }],
      }, 401);
      return true;
    }
    const method = String(req.method || "GET").toUpperCase();
    const expectedOrigin = `http://${req.headers.host || `${config.host}:${config.port}`}`;
    const forceRefresh = url.searchParams.get("refresh") === "1";
    const cachedData = (key, command, extra, policy) => responseCache.get(
      key,
      () => runData(command, forceRefresh ? [...extra, "--refresh"] : extra),
      policy,
      { force: forceRefresh },
    );
    try {
      let payload;
      if (method === "GET" && url.pathname === "/api/portfolio") {
        payload = await cachedData("portfolio", "portfolio", [], READ_POLICIES.portfolio);
      } else if (method === "GET" && url.pathname === "/api/watchlist") {
        payload = await cachedData("watchlist", "watchlist", [], READ_POLICIES.watchlist);
      } else if (method === "GET" && url.pathname === "/api/stock/context") {
        const code = queryValue(url, "code");
        payload = await cachedData(`stock-context:${code}`, "stock-context", [code], READ_POLICIES.stock);
      } else if (method === "GET" && url.pathname === "/api/stock/financials") {
        const code = queryValue(url, "code");
        const period = queryValue(url, "period", "annual");
        payload = await cachedData(`stock-financials:${code}:${period}`, "stock-financials", [code, "--period", period], READ_POLICIES.financials);
      } else if (method === "GET" && url.pathname === "/api/stock/flow") {
        const code = queryValue(url, "code");
        payload = await cachedData(`stock-flow:${code}`, "stock-flow", [code], READ_POLICIES.stock);
      } else if (method === "GET" && url.pathname === "/api/stock/intel") {
        const code = queryValue(url, "code");
        const kind = queryValue(url, "kind", "all");
        payload = await cachedData(`stock-intel:${code}:${kind}`, "stock-intel", [code, "--kind", kind], READ_POLICIES.intel);
      } else if (method === "GET" && url.pathname === "/api/stock/options") {
        const code = queryValue(url, "code");
        payload = await cachedData(`stock-options:${code}`, "stock-options", [code], READ_POLICIES.stock);
      } else if (method === "GET" && url.pathname === "/api/daily-review") {
        const market = queryValue(url, "market", "A");
        payload = await cachedData(`daily-review:${market}`, "daily-review", ["--market", market], READ_POLICIES.daily);
      } else if (method === "GET" && url.pathname === "/api/intel") {
        const scope = queryValue(url, "scope", "all");
        const market = queryValue(url, "market", "all");
        const kind = queryValue(url, "kind", "all");
        payload = await cachedData(`intel:${scope}:${market}:${kind}`, "intel", [
          "--scope", scope,
          "--market", market,
          "--kind", kind,
        ], READ_POLICIES.intel);
      } else if (method === "GET" && url.pathname === "/api/sectors") {
        const extra = url.searchParams.get("include_archived") === "1" ? ["--include-archived"] : [];
        payload = await runData("sectors", extra);
      } else if (method === "POST" && url.pathname === "/api/sectors") {
        assertJsonWrite(req, expectedOrigin);
        payload = await runData("sector-mutate", ["create"], JSON.stringify(await readJson(req)));
      } else if (/^\/api\/sectors\/\d+$/.test(url.pathname)) {
        const sectorId = url.pathname.split("/").at(-1);
        if (method === "GET") {
          payload = await runData("sector", [sectorId]);
        } else if (method === "PATCH" || method === "DELETE") {
          assertJsonWrite(req, expectedOrigin);
          const body = method === "PATCH" ? await readJson(req) : {};
          body.sector_id = Number(sectorId);
          payload = await runData("sector-mutate", [method === "PATCH" ? "update" : "archive"], JSON.stringify(body));
        }
      } else if (/^\/api\/sectors\/\d+\/(tags|nodes|edges|symbols|knowledge)(\/[^/]+)?$/.test(url.pathname)) {
        assertJsonWrite(req, expectedOrigin);
        const parts = url.pathname.split("/").filter(Boolean);
        const sectorId = Number(parts[2]);
        const resource = parts[3];
        const itemId = parts[4];
        const body = method === "DELETE" ? {} : await readJson(req);
        body.sector_id = sectorId;
        if (itemId) {
          if (resource === "symbols") body.ts_code = decodeURIComponent(itemId);
          else body.item_id = Number(itemId);
        }
        const action = method === "POST" ? `${resource.replace(/s$/, "")}-add`
          : method === "PATCH" ? `${resource.replace(/s$/, "")}-update`
            : method === "DELETE" ? `${resource.replace(/s$/, "")}-delete` : "";
        const normalizedAction = action.replace("tag-add", "tag-add").replace("node-add", "node-add")
          .replace("edge-add", "edge-add").replace("symbol-add", "symbol-add")
          .replace("knowledge-add", "knowledge-add");
        if (!normalizedAction || (method !== "POST" && method !== "PATCH" && method !== "DELETE")) {
          const error = new Error("method not allowed");
          error.status = 405;
          error.code = "METHOD_NOT_ALLOWED";
          throw error;
        }
        payload = await runData("sector-mutate", [normalizedAction], JSON.stringify(body));
      } else if (method === "POST" && url.pathname === "/api/research-records") {
        assertJsonWrite(req, expectedOrigin);
        payload = await runData("research-save", [], JSON.stringify(await readJson(req)));
      } else if (method === "GET" && url.pathname === "/api/research-records") {
        const extra = [];
        for (const [query, flag] of [["scope_type", "--scope-type"], ["ts_code", "--ts-code"], ["sector_id", "--sector-id"]]) {
          if (url.searchParams.has(query)) extra.push(flag, queryValue(url, query));
        }
        payload = await runData("research-list", extra);
      } else if (method === "DELETE" && /^\/api\/research-records\/\d+$/.test(url.pathname)) {
        assertJsonWrite(req, expectedOrigin);
        const recordId = Number(url.pathname.split("/").at(-1));
        payload = await runData("research-delete", [], JSON.stringify({ record_id: recordId }));
      } else if (method === "DELETE" && url.pathname === "/api/research-records") {
        assertJsonWrite(req, expectedOrigin);
        const body = await readJson(req);
        if (body.all !== true) {
          const error = new Error("清空研究记录需要 all=true");
          error.status = 400;
          error.code = "INVALID_INPUT";
          throw error;
        }
        payload = await runData("research-delete", [], JSON.stringify({ all: true }));
      } else if (method === "GET" && url.pathname === "/api/ai/capabilities") {
        payload = await cachedData("ai-capabilities", "ai-capabilities", [], READ_POLICIES.capabilities);
      } else if (method === "POST" && url.pathname === "/api/chat") {
        assertJsonWrite(req, expectedOrigin);
        const body = await readJson(req, 512 * 1024);
        await streamPythonNdjson({
          req,
          res,
          python: config.python,
          script: config.dashboardChatScript,
          args: ["--workspace", config.workspace],
          input: body,
        });
        return true;
      } else {
        return false;
      }
      if (!payload) return false;
      sendJson(res, payload, workerStatus(payload));
      return true;
    } catch (error) {
      const result = publicError(error);
      sendJson(res, result.payload, result.status);
      return true;
    }
  }

  return { handle };
}
