import http from "node:http";
import { execFile } from "node:child_process";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import { fileURLToPath } from "node:url";

const home = os.homedir();
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const workspace = process.env.STJ_WORKSPACE || path.join(home, ".trade-journal");
const dbPath = process.env.STJ_DB || path.join(workspace, "results", "trade-journal", "db", "trades.db");
const chartDir = path.join(workspace, "results", "trade-journal", "charts");
const liveDataDir = path.join(chartDir, "live-data");
const renderChartScript = process.env.STJ_RENDER_CHART ||
  path.join(scriptDir, "render_chart.py");
const port = Number(process.env.PORT || 8787);
const host = process.env.HOST || "127.0.0.1";
const periods = new Set(["1w", "1mo", "3mo", "6mo", "1y", "3y", "trade"]);
const quoteTimeoutMs = Number(process.env.STJ_QUOTE_TIMEOUT_MS || 1800);

function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    execFile(command, args, { maxBuffer: 10 * 1024 * 1024, ...options }, (error, stdout, stderr) => {
      if (error) {
        error.message = `${error.message}\n${stderr || ""}`;
        reject(error);
        return;
      }
      resolve(stdout);
    });
  });
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function sqliteJson(sql) {
  const out = await run("sqlite3", ["-json", dbPath, sql]);
  return out.trim() ? JSON.parse(out) : [];
}

function h(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function fixed(value, digits = 3) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toFixed(digits);
}

function signedFixed(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const num = Number(value);
  return `${num >= 0 ? "+" : ""}${num.toFixed(digits)}`;
}

function marketOf(code) {
  const parts = String(code).split(".");
  return parts.length > 1 ? parts.at(-1).toUpperCase() : "US";
}

function eastmoneySecid(item) {
  const code = String(item.ts_code || "");
  const symbol = code.split(".")[0];
  const market = marketOf(code);
  const exchange = String(item.exchange || "").toUpperCase();
  if (market === "SZ") return `0.${symbol}`;
  if (market === "SH") return `1.${symbol}`;
  if (market === "HK") return `116.${symbol.padStart(5, "0")}`;
  if (market === "US") return `${exchange === "NYSE" ? "106" : "105"}.${symbol.toUpperCase()}`;
  return null;
}

function yahooSymbol(code) {
  const [symbol, market] = String(code).split(".");
  if (market === "HK") return `${symbol.padStart(4, "0")}.HK`;
  if (market === "SH") return `${symbol}.SS`;
  if (market === "SZ") return `${symbol}.SZ`;
  return symbol;
}

function formatQuoteTime(unixSeconds) {
  if (!unixSeconds) return "-";
  return new Date(unixSeconds * 1000).toLocaleString("zh-CN", { hour12: false });
}

async function fetchJson(url, timeoutMs = quoteTimeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: { "user-agent": "Mozilla/5.0 stj-live-node/1.0" },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

function dateKey(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}${m}${d}`;
}

async function periodStartDate(code, period) {
  if (period === "trade") {
    const rows = await sqliteJson(`
      SELECT MIN(timestamp) AS first_ts
      FROM trades
      WHERE ts_code = '${String(code).replaceAll("'", "''")}'
    `);
    const first = rows[0]?.first_ts ? new Date(rows[0].first_ts) : null;
    if (first && !Number.isNaN(first.getTime())) {
      first.setDate(first.getDate() - 5);
      return first;
    }
  }
  const days = {
    "1w": 10,
    "1mo": 35,
    "3mo": 100,
    "6mo": 190,
    "1y": 370,
    "3y": 1110,
  }[period] || 370;
  const start = new Date();
  start.setDate(start.getDate() - days);
  return start;
}

async function securityRow(code) {
  const escaped = String(code).replaceAll("'", "''");
  const rows = await sqliteJson(`
    SELECT ts_code, exchange, NULL AS name FROM positions WHERE ts_code = '${escaped}'
    UNION ALL
    SELECT ts_code, exchange, name FROM watchlist WHERE ts_code = '${escaped}'
    LIMIT 1
  `);
  return rows[0] || { ts_code: code, exchange: "" };
}

async function fetchEastmoneyOhlc(code, period) {
  const item = await securityRow(code);
  const secid = eastmoneySecid(item);
  if (!secid) throw new Error(`unsupported Eastmoney symbol: ${code}`);
  const start = await periodStartDate(code, period);
  const url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + new URLSearchParams({
    secid,
    fields1: "f1,f2,f3,f4,f5,f6",
    fields2: "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    klt: "101",
    fqt: "1",
    beg: dateKey(start),
    end: dateKey(new Date()),
  });
  const data = await fetchJson(url, 8000);
  const klines = data?.data?.klines || [];
  if (!klines.length) throw new Error(`empty Eastmoney klines: ${secid}`);
  return klines.map((line) => {
    const [date, open, close, high, low, volume] = String(line).split(",");
    return {
      date: new Date(`${date}T00:00:00Z`).toISOString(),
      open: Number(open),
      high: Number(high),
      low: Number(low),
      close: Number(close),
      volume: Number(volume),
    };
  }).filter((row) => Number.isFinite(row.close));
}

async function fetchYahooOhlc(code, period) {
  const start = await periodStartDate(code, period);
  const params = new URLSearchParams({
    interval: "1d",
    events: "history",
    includeAdjustedClose: "true",
    period1: String(Math.floor(start.getTime() / 1000)),
    period2: String(Math.floor(Date.now() / 1000)),
  });
  const url = `https://query2.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(yahooSymbol(code))}?${params}`;
  const data = await fetchJson(url, 8000);
  const result = data?.chart?.result?.[0];
  const timestamps = result?.timestamp || [];
  const quote = result?.indicators?.quote?.[0] || {};
  const records = timestamps.map((ts, idx) => {
    const close = quote.close?.[idx];
    if (close == null) return null;
    return {
      date: new Date(ts * 1000).toISOString(),
      open: quote.open?.[idx] ?? close,
      high: quote.high?.[idx] ?? close,
      low: quote.low?.[idx] ?? close,
      close,
      volume: quote.volume?.[idx] ?? null,
    };
  }).filter(Boolean);
  if (!records.length) throw new Error(`empty Yahoo klines: ${code}`);
  return records;
}

async function buildPriceJson(code, period) {
  let records;
  try {
    records = await fetchEastmoneyOhlc(code, period);
  } catch (eastmoneyError) {
    records = await fetchYahooOhlc(code, period);
  }
  await mkdir(liveDataDir, { recursive: true });
  const safe = code.replaceAll("/", "_").replaceAll(":", "_");
  const file = path.join(liveDataDir, `${safe}-${period}.json`);
  await writeFile(file, JSON.stringify({ data: records }, null, 2), "utf8");
  return file;
}

async function fetchQuotes(items) {
  const quotes = new Map();
  const secids = items.map(eastmoneySecid).filter(Boolean);
  if (secids.length) {
    const url = "https://push2.eastmoney.com/api/qt/ulist.np/get?" + new URLSearchParams({
      fltt: "2",
      fields: "f12,f13,f14,f2,f3,f4,f124",
      secids: secids.join(","),
    });
    try {
      const data = await fetchJson(url);
      for (const row of data?.data?.diff || []) {
        const found = items.find((item) => eastmoneySecid(item) === `${row.f13}.${row.f12}`);
        if (found && row.f2 !== "-") {
          quotes.set(found.ts_code, {
            price: row.f2,
            pct: row.f3,
            change: row.f4,
            name: row.f14,
            source: "东方财富",
            time: formatQuoteTime(row.f124),
          });
        }
      }
    } catch {
      // Fallback below handles missing quotes.
    }
  }

  await Promise.all(items.map(async (item) => {
    if (quotes.has(item.ts_code)) return;
    const symbol = yahooSymbol(item.ts_code);
    try {
      const url = `https://query2.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?range=5d&interval=1d`;
      const data = await fetchJson(url);
      const meta = data?.chart?.result?.[0]?.meta;
      if (meta?.regularMarketPrice != null) {
        quotes.set(item.ts_code, {
          price: meta.regularMarketPrice,
          pct: null,
          change: null,
          name: meta.shortName || item.name || item.ts_code,
          source: "Yahoo",
          time: meta.regularMarketTime ? formatQuoteTime(meta.regularMarketTime) : "-",
        });
      }
    } catch {
      quotes.set(item.ts_code, { price: "-", pct: null, change: null, name: item.name || item.ts_code, source: "未确认", time: "-" });
    }
  }));
  for (const item of items) {
    if (!quotes.has(item.ts_code)) {
      quotes.set(item.ts_code, { price: "-", pct: null, change: null, name: item.name || item.ts_code, source: "未确认", time: "-" });
    }
  }
  return quotes;
}

async function loadData() {
  const positions = await sqliteJson(`
    SELECT ts_code, exchange, quantity, avg_cost, total_cost, realized_pnl, currency, last_trade_date
    FROM positions
    WHERE quantity != 0
    ORDER BY ts_code
  `);
  const watches = await sqliteJson(`
    SELECT w.ts_code, w.exchange, w.name, w.category, w.target_price, w.stop_loss, w.priority, w.status, w.updated_at,
           (SELECT COUNT(*) FROM notes n WHERE n.ts_code = w.ts_code AND n.note_type = 'watch_observation') AS note_count
    FROM watchlist w
    WHERE w.status != 'removed'
    ORDER BY w.priority DESC, w.updated_at DESC, w.id DESC
  `);
  const all = [...positions, ...watches.filter((w) => !positions.some((p) => p.ts_code === w.ts_code))];
  const quotes = await fetchQuotes(all);
  return { positions, watches, quotes };
}

function pctClass(value) {
  return Number(value) >= 0 ? "up" : "down";
}

function quoteCell(code, quotes) {
  const quote = quotes.get(code) || {};
  const pct = quote.pct == null ? "" : ` <span class="${pctClass(quote.pct)}">${Number(quote.pct).toFixed(2)}%</span>`;
  const price = quote.price === "-" || quote.price === undefined ? "-" : fixed(quote.price, 3);
  return `<div class="quote-price">${h(price)}${pct}</div><div class="muted">${h(quote.source || "-")} ${h(quote.time || "-")}</div>`;
}

function positionReturn(position, quotes) {
  const quote = quotes.get(position.ts_code) || {};
  const price = Number(quote.price);
  const quantity = Number(position.quantity);
  const cost = Number(position.total_cost ?? (Number(position.avg_cost) * quantity));
  if (!Number.isFinite(price) || !Number.isFinite(quantity) || !Number.isFinite(cost) || !cost) {
    return { pnl: null, pct: null, cls: "" };
  }
  const realized = Number(position.realized_pnl || 0);
  const pnl = price * quantity - cost + realized;
  return {
    pnl,
    pct: (pnl / cost) * 100,
    cls: pnl >= 0 ? "up" : "down",
    hasRealized: realized !== 0,
  };
}

function returnRateCell(position, quotes) {
  const result = positionReturn(position, quotes);
  if (result.pct == null) return `<span class="muted">-</span>`;
  return `<span class="${result.cls}">${h(signedFixed(result.pct, 2))}%</span>`;
}

function totalReturnCell(position, quotes) {
  const result = positionReturn(position, quotes);
  if (result.pnl == null) return `<span class="muted">-</span>`;
  const note = result.hasRealized ? `<div class="muted">含已实现</div>` : "";
  return `<div class="${result.cls}">${h(signedFixed(result.pnl, 2))} ${h(position.currency || "")}</div>${note}`;
}

function chartLink(code, period = "1y") {
  return `/chart?code=${encodeURIComponent(code)}&period=${encodeURIComponent(period)}`;
}

function renderIndex({ positions, watches, quotes }) {
  const now = new Date().toLocaleString("zh-CN", { hour12: false });
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>STJ 实时持仓与关注</title>
  <style>
    body{margin:0;background:#f7f8fa;color:#171717;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    main{width:min(1320px,calc(100vw - 64px));margin:0 auto;padding:24px 0}
    header{display:flex;justify-content:space-between;gap:16px;align-items:flex-end;margin-bottom:18px}
    h1{font-size:24px;margin:0 0 6px}.muted{color:#737373;font-size:12px;line-height:1.5}
    .actions,.chart-actions{display:flex;gap:8px;flex-wrap:nowrap}.btn{display:inline-flex;align-items:center;justify-content:center;min-height:30px;border:1px solid #d4d4d4;background:white;border-radius:6px;padding:6px 10px;color:#171717;text-decoration:none;font-size:13px;line-height:1;white-space:nowrap}
    section{background:white;border:1px solid #e5e5e5;border-radius:8px;margin:14px 0;overflow-x:auto;overflow-y:hidden}
    h2{font-size:15px;margin:0;padding:13px 16px;border-bottom:1px solid #eee;background:#fbfbfb}
    table{width:100%;min-width:1120px;border-collapse:collapse;font-size:13px;table-layout:fixed}th,td{padding:10px 12px;border-top:1px solid #f1f1f1;text-align:left;vertical-align:middle}
    th{font-size:12px;color:#737373;font-weight:600}.num{text-align:right;font-variant-numeric:tabular-nums}.up{color:#c62828;font-weight:700}.down{color:#098658;font-weight:700}
    .code-col{width:130px}.exchange-col{width:96px}.qty-col{width:86px}.cost-col{width:132px}.return-col{width:108px}.pnl-col{width:142px}.price-col{width:190px}.chart-col{width:180px}.watch-target-col{width:150px}
    .code{font-weight:700}.muted{word-break:break-word}.quote-price{font-weight:700}
    @media(max-width:760px){main{width:auto;padding:12px}header{display:block}table{font-size:12px;table-layout:auto;min-width:920px}.exchange-col,.cost-col,th.exchange-col,td.exchange-col,th.cost-col,td.cost-col{display:none}.chart-actions{gap:6px}.btn{padding:6px 8px}}
  </style>
</head>
<body><main>
  <header>
    <div><h1>STJ 实时持仓与关注</h1><div class="muted">页面刷新时读取 SQLite；报价来自东方财富/Yahoo；单只图表点击时实时调用 skill 生成 HTML。更新时间：${h(now)}</div></div>
    <div class="actions"><a class="btn" href="/">刷新</a><a class="btn" href="/api/data">JSON</a></div>
  </header>
  <section>
    <h2>持仓</h2>
    <table><thead><tr><th class="code-col">代码</th><th class="exchange-col">交易所</th><th class="num qty-col">数量</th><th class="num cost-col">成本</th><th class="num return-col">收益率</th><th class="num pnl-col">总收益</th><th class="num price-col">实时价</th><th class="chart-col">图表</th></tr></thead><tbody>
      ${positions.map((p) => `<tr>
        <td class="code">${h(p.ts_code)}</td><td class="exchange-col">${h(p.exchange || "-")}</td>
        <td class="num">${h(p.quantity)}</td><td class="num cost-col">${h(fixed(p.avg_cost, 3))} ${h(p.currency || "")}</td>
        <td class="num return-col">${returnRateCell(p, quotes)}</td>
        <td class="num pnl-col">${totalReturnCell(p, quotes)}</td>
        <td class="num">${quoteCell(p.ts_code, quotes)}</td>
        <td><div class="chart-actions"><a class="btn" href="${chartLink(p.ts_code, "trade")}">交易以来</a><a class="btn" href="${chartLink(p.ts_code, "1y")}">1年</a></div></td>
      </tr>`).join("") || `<tr><td colspan="8">无持仓</td></tr>`}
    </tbody></table>
  </section>
  <section>
    <h2>关注列表</h2>
    <table><thead><tr><th class="code-col">代码</th><th>名称/分类</th><th class="num watch-target-col">目标/止损</th><th class="num price-col">实时价</th><th class="chart-col">图表</th></tr></thead><tbody>
      ${watches.map((w) => `<tr>
        <td><strong>${h(w.ts_code)}</strong><div class="muted">${h(w.status)} · 笔记 ${h(w.note_count || 0)}</div></td>
        <td>${h(w.name || "-")}<div class="muted">${h(w.category || "-")} · ${h(w.exchange || "-")}</div></td>
        <td class="num">${h(w.target_price ?? "-")} / ${h(w.stop_loss ?? "-")}</td>
        <td class="num">${quoteCell(w.ts_code, quotes)}</td>
        <td><div class="chart-actions"><a class="btn" href="${chartLink(w.ts_code, "6mo")}">6月</a><a class="btn" href="${chartLink(w.ts_code, "1y")}">1年</a></div></td>
      </tr>`).join("") || `<tr><td colspan="5">无关注标的</td></tr>`}
    </tbody></table>
  </section>
</main></body></html>`;
}

async function generateChart(code, period) {
  if (!/^[A-Za-z0-9_.-]+$/.test(code)) throw new Error("invalid code");
  if (!periods.has(period)) throw new Error("invalid period");
  const safe = code.replaceAll("/", "_").replaceAll(":", "_");
  const out = path.join(chartDir, `live-${safe}-${period}.html`);
  let lastError;
  for (let attempt = 1; attempt <= 2; attempt += 1) {
    try {
      const priceJson = await buildPriceJson(code, period);
      await run("python3", [renderChartScript, code, "--period", period, "--price-json", priceJson, "--output", out, "--no-latest"]);
      return `/charts/${encodeURIComponent(path.basename(out))}?t=${Date.now()}`;
    } catch (error) {
      lastError = error;
      await delay(300 * attempt);
    }
  }
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      await run("python3", [renderChartScript, code, "--period", period, "--output", out, "--no-latest"]);
      return `/charts/${encodeURIComponent(path.basename(out))}?t=${Date.now()}`;
    } catch (error) {
      lastError = error;
      await delay(400 * attempt);
    }
  }
  try {
    await stat(out);
  } catch {
    throw lastError;
  }
  return `/charts/${encodeURIComponent(path.basename(out))}?t=${Date.now()}`;
}

async function serveStaticChart(req, res, pathname) {
  const name = decodeURIComponent(pathname.replace("/charts/", ""));
  const file = path.normalize(path.join(chartDir, name));
  if (!file.startsWith(path.normalize(chartDir + path.sep))) throw new Error("invalid chart path");
  await stat(file);
  const ext = path.extname(file);
  res.setHeader("content-type", ext === ".js" ? "text/javascript; charset=utf-8" : "text/html; charset=utf-8");
  res.end(await readFile(file));
}

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url || "/", `http://${req.headers.host || `${host}:${port}`}`);
    if (url.pathname === "/") {
      const data = await loadData();
      res.setHeader("content-type", "text/html; charset=utf-8");
      res.end(renderIndex(data));
      return;
    }
    if (url.pathname === "/api/data") {
      const data = await loadData();
      res.setHeader("content-type", "application/json; charset=utf-8");
      res.end(JSON.stringify({
        positions: data.positions,
        watches: data.watches,
        quotes: Object.fromEntries(data.quotes),
      }, null, 2));
      return;
    }
    if (url.pathname === "/chart") {
      const code = url.searchParams.get("code") || "";
      const period = url.searchParams.get("period") || "1y";
      const target = await generateChart(code, period);
      res.statusCode = 302;
      res.setHeader("location", target);
      res.end();
      return;
    }
    if (url.pathname.startsWith("/charts/")) {
      await serveStaticChart(req, res, url.pathname);
      return;
    }
    res.statusCode = 404;
    res.end("not found");
  } catch (error) {
    res.statusCode = 500;
    res.setHeader("content-type", "text/plain; charset=utf-8");
    res.end(String(error?.stack || error));
  }
});

server.listen(port, host, () => {
  console.log(`STJ live server: http://${host}:${port}`);
  console.log(`DB: ${dbPath}`);
  console.log(`render_chart.py: ${renderChartScript}`);
});
