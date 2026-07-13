import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import http from "node:http";
import net from "node:net";
import { spawn } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { authorize, isLoopbackHost } from "../scripts/live/http_helpers.mjs";
import { createResponseCache } from "../scripts/live/api_routes.mjs";
import { runPythonJson } from "../scripts/live/python_bridge.mjs";


const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const serverScript = path.join(root, "scripts", "live_server.mjs");


async function freePort() {
  const server = net.createServer();
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;
  await new Promise((resolve) => server.close(resolve));
  return port;
}


async function startServer({ apiKey = "", dashboardV2 = "1" } = {}) {
  const workspace = await mkdtemp(path.join(tmpdir(), "stj-live-test-"));
  const port = await freePort();
  const child = spawn(process.execPath, [serverScript], {
    cwd: root,
    env: {
      ...process.env,
      PORT: String(port),
      HOST: "127.0.0.1",
      STJ_WORKSPACE: workspace,
      STJ_DASHBOARD_V2: dashboardV2,
      STJ_API_KEY: apiKey,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let output = "";
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`server start timeout: ${output}`)), 8000);
    child.stdout.on("data", (chunk) => {
      output += chunk.toString("utf8");
      if (output.includes("STJ live server:")) {
        clearTimeout(timer);
        resolve();
      }
    });
    child.stderr.on("data", (chunk) => { output += chunk.toString("utf8"); });
    child.on("exit", (code) => reject(new Error(`server exited ${code}: ${output}`)));
  });
  return {
    base: `http://127.0.0.1:${port}`,
    child,
    workspace,
    async close() {
      child.kill("SIGTERM");
      await new Promise((resolve) => child.once("exit", resolve));
      await rm(workspace, { recursive: true, force: true });
    },
  };
}


test("loopback and bearer helpers", () => {
  assert.equal(isLoopbackHost("127.0.0.1"), true);
  assert.equal(isLoopbackHost("0.0.0.0"), false);
  assert.equal(authorize({ headers: { authorization: "Bearer abc" } }, "abc"), true);
  assert.equal(authorize({ headers: { authorization: "Bearer no" } }, "abc"), false);
});


test("python bridge parses structured output without shell", async () => {
  const payload = await runPythonJson({
    script: "-c",
    args: ["import json; print(json.dumps({'ok': True, 'data': {'value': 7}}))"],
  });
  assert.equal(payload.data.value, 7);
});


test("response cache serves stale immediately and refreshes in background", async () => {
  let clock = 0;
  let version = 1;
  const cache = createResponseCache({ now: () => clock });
  const load = async () => ({ ok: true, data: { version }, meta: { cache: { hit: false, stale: false } }, errors: [] });
  const policy = { freshMs: 10, staleMs: 1000 };
  assert.equal((await cache.get("k", load, policy)).data.version, 1);
  clock = 20;
  version = 2;
  const stale = await cache.get("k", load, policy);
  assert.equal(stale.data.version, 1);
  assert.equal(stale.meta.response_cache.stale, true);
  await new Promise((resolve) => setImmediate(resolve));
  const refreshed = await cache.get("k", load, policy);
  assert.equal(refreshed.data.version, 2);
  assert.equal(refreshed.meta.response_cache.stale, false);
});


test("dashboard shell, assets, portfolio and sector write", async (t) => {
  const server = await startServer();
  t.after(() => server.close());
  const page = await fetch(`${server.base}/`);
  assert.equal(page.status, 200);
  const pageHtml = await page.text();
  assert.match(pageHtml, /STJ 投研工作台/);
  assert.match(pageHtml, /AI 数据工具是什么/);
  assert.match(pageHtml, /默认回答结构/);
  assert.match(pageHtml, /AI 当日复盘/);
  assert.match(pageHtml, /一键提炼全部要点/);
  assert.match(pageHtml, /研究记录/);
  assert.match(pageHtml, /接入能力对比/);
  assert.match(pageHtml, /thinking-orb/);
  assert.match(pageHtml, /breadth-bar/);
  assert.match(pageHtml, /market-leaders/);
  assert.match(pageHtml, /row\.asset\.ts_code/);
  assert.match(pageHtml, /长度按本组最大绝对值归一/);
  assert.doesNotMatch(pageHtml, /src="\/assets\/echarts\.min\.js"/);
  const asset = await fetch(`${server.base}/assets/dashboard.js`);
  assert.equal(asset.status, 200);
  assert.match(asset.headers.get("content-type"), /javascript/);
  const assetText = await asset.text();
  assert.match(assetText, /function ensureEcharts/);
  assert.match(assetText, /void this\.loadAiCapabilities\(\)/);
  const style = await fetch(`${server.base}/assets/dashboard.css`);
  assert.equal(style.status, 200);
  assert.match(await style.text(), /\.market-leader\s*\{/);
  const portfolio = await fetch(`${server.base}/api/portfolio`).then((response) => response.json());
  assert.equal(portfolio.ok, true);
  assert.deepEqual(portfolio.data.positions, []);
  const cachedPortfolio = await fetch(`${server.base}/api/portfolio`).then((response) => response.json());
  assert.equal(cachedPortfolio.meta.response_cache.hit, true);
  const sector = await fetch(`${server.base}/api/sectors`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: "测试板块", summary: "fixture" }),
  }).then((response) => response.json());
  assert.equal(sector.ok, true);
  assert.equal(sector.data.name, "测试板块");
  const updated = await fetch(`${server.base}/api/sectors/${sector.data.id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: "已更新板块", summary: "edited" }),
  }).then((response) => response.json());
  assert.equal(updated.data.name, "已更新板块");
  const archived = await fetch(`${server.base}/api/sectors/${sector.data.id}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  }).then((response) => response.json());
  assert.equal(archived.data.status, "archived");
  const restored = await fetch(`${server.base}/api/sectors/${sector.data.id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: "active" }),
  }).then((response) => response.json());
  assert.equal(restored.data.status, "active");
  const traversal = await fetch(`${server.base}/assets/not-allowed.js`);
  assert.equal(traversal.status, 404);
});


test("optional STJ_API_KEY protects APIs", async (t) => {
  const server = await startServer({ apiKey: "test-secret" });
  t.after(() => server.close());
  const denied = await fetch(`${server.base}/api/portfolio`);
  assert.equal(denied.status, 401);
  const allowed = await fetch(`${server.base}/api/portfolio`, { headers: { Authorization: "Bearer test-secret" } });
  assert.equal(allowed.status, 200);
});


test("research records support save, list, single delete and clear", async (t) => {
  const server = await startServer();
  t.after(() => server.close());
  const save = async (question) => fetch(`${server.base}/api/research-records`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scope_type: "page", question, answer: `${question}的答案`, sources: [] }),
  }).then((response) => response.json());
  const first = await save("第一条");
  await save("第二条");
  assert.equal(first.ok, true);
  let records = await fetch(`${server.base}/api/research-records`).then((response) => response.json());
  assert.equal(records.data.records.length, 2);
  const deleted = await fetch(`${server.base}/api/research-records/${first.data.id}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  }).then((response) => response.json());
  assert.equal(deleted.data.deleted, true);
  const cleared = await fetch(`${server.base}/api/research-records`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ all: true }),
  }).then((response) => response.json());
  assert.equal(cleared.data.deleted, 1);
  records = await fetch(`${server.base}/api/research-records`).then((response) => response.json());
  assert.deepEqual(records.data.records, []);
});


test("legacy homepage and /api/data remain available behind the feature flag", async (t) => {
  const server = await startServer({ dashboardV2: "0" });
  t.after(() => server.close());
  // The structured endpoint performs the same additive schema initialization
  // that a normal, already-existing STJ workspace has before legacy rendering.
  assert.equal((await fetch(`${server.base}/api/portfolio`)).status, 200);
  const page = await fetch(`${server.base}/`);
  assert.equal(page.status, 200);
  assert.match(await page.text(), /STJ 实时持仓与关注/);
  const legacy = await fetch(`${server.base}/api/data`);
  assert.equal(legacy.status, 200);
  assert.deepEqual(await legacy.json(), { positions: [], watches: [], quotes: {} });
});


test("OpenAI-compatible chat streams end to end without echoing the key", async (t) => {
  let authorization = "";
  const fake = http.createServer((req, res) => {
    authorization = String(req.headers.authorization || "");
    req.resume();
    req.on("end", () => {
      const event = JSON.stringify({ choices: [{ delta: { content: "API_OK" } }] });
      const body = `data: ${event}\n\ndata: [DONE]\n\n`;
      res.writeHead(200, { "Content-Type": "text/event-stream", "Content-Length": Buffer.byteLength(body) });
      res.end(body);
    });
  });
  await new Promise((resolve) => fake.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise((resolve) => fake.close(resolve)));
  const server = await startServer();
  t.after(() => server.close());
  const secret = "ephemeral-test-key";
  const response = await fetch(`${server.base}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      messages: [{ role: "user", content: "只回复 API_OK" }],
      context: {
        page: "positions",
        include: { portfolio: false, watchlist: false, notes: false, news: false, sector: false },
      },
      llm: {
        mode: "api",
        provider: "openai-compatible",
        model: "fixture-model",
        baseURL: `http://127.0.0.1:${fake.address().port}`,
        apiKey: secret,
      },
    }),
  });
  assert.equal(response.status, 200);
  const stream = await response.text();
  const events = stream.trim().split("\n").map((line) => JSON.parse(line));
  assert.deepEqual(events.map((event) => event.type), ["meta", "delta", "done"]);
  assert.equal(events[1].text, "API_OK");
  assert.equal(authorization, `Bearer ${secret}`);
  assert.equal(stream.includes(secret), false);
});
