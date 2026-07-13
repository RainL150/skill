# STJ Dashboard Cross-Layer Contract

## Scenario: Extend the local investment dashboard

### 1. Scope / Trigger

Use this contract when changing `stock-trade-journal` dashboard data, HTTP routes, sector/research
storage, or Ask AI. These paths cross SQLite → Python service → Node API → Alpine UI, so a field or
error change must be updated and tested across every layer.

### 2. Signatures

- Data CLI: `python3 scripts/dashboard_data.py <command> [args] --workspace <path> --json`.
- Chat CLI: `python3 scripts/dashboard_chat.py --workspace <path>`; request is one stdin JSON object,
  response is stdout NDJSON.
- HTTP reads: `GET /api/portfolio`, `/api/watchlist`, `/api/stock/*`, `/api/daily-review`,
  `/api/intel`, `/api/sectors`, `/api/ai/capabilities`, `/api/research-records`.
- HTTP writes: sector `POST/PATCH/DELETE`, explicit research-record `POST`, single/clear research-record
  `DELETE`, and `POST /api/chat`.
- Schema owner remains `scripts/db_schema.py`; dashboard tables are `sectors`, `sector_tags`,
  `sector_nodes`, `sector_edges`, `sector_symbols`, `sector_knowledge`, and `research_records`.

### 3. Contracts

Every data response uses `dashboard-v1`:

```json
{
  "ok": true,
  "data": {},
  "meta": {
    "contract_version": "dashboard-v1",
    "generated_at": "ISO-8601",
    "as_of": "ISO-8601",
    "sources": [],
    "cache": {"hit": false, "stale": false, "age_seconds": 0},
    "warnings": [],
    "status": 200
  },
  "errors": []
}
```

- Numbers stay numeric; missing/non-finite values become `null`, never `0` or `NaN` by default.
- Browser context contains only trusted descriptors (`page`, `ts_code`, `sector_id`, filters, boolean
  include/style preferences). Python reloads all facts.
- Chat event types are `meta`, `delta`, `tool_start`, `tool_result`, `done`, `error`.
- `meta` identifies the runtime that actually handled the request (`provider`, `model`, `model_label`,
  `runtime_kind`, `mode`). The UI snapshots the submitted configuration per message, so switching the
  current setting cannot relabel an older Claude response as Codex or vice versa.
- A streamed assistant message must be looked up and mutated through Alpine's reactive collection after
  insertion. Do not keep mutating the pre-insertion plain object: the backend may finish correctly while
  the drawer remains blank. Before the first delta, show an animated processing state and the latest
  `status` event; partial text shows a streaming caret.
- The drawer shows trusted context preview, page-specific suggestions, tool arguments/results/sources,
  stop/retry, and explicit save. Closing the drawer aborts an active stream.
- Daily review and intel may start explicit inline chat streams. Intel bulk summarize performs the
  `holding`, `watch`, and `investment` scopes sequentially and never runs without a user click.
- Research records are never automatic. `DELETE /api/research-records/:id` deletes one row;
  `DELETE /api/research-records` requires JSON `{ "all": true }` before clearing all rows.
- API mode may use the nine allowlisted read-only tools. CLI mode receives preloaded context and zero tools.
- Claude Code uses `stream-json` with partial assistant events; its parser emits only text deltas and
  suppresses duplicate final `assistant`/`result` payloads. CLI provider/model pairs are validated exactly
  (`claude-code` → Claude, `codex` → Codex) before a child process is started.
- A-share market temperature is market breadth from a dedicated up/down/flat source, not the sign of a
  hand-picked industry-flow list. If breadth is unavailable, the response and UI must say `proxy` and name
  the proxy basis. A-share industry rotation contains both inflow and outflow extremes, and bar length is
  normalized against the largest absolute value in the displayed set; the centre axis encodes direction.
- The A-share breadth card may include `leaders`, but they must come from a separately sourced company
  gainers ranking. Every row carries normalized `asset`, price, change, industry, source and `as_of`; exclude
  listing-day/early-listing and delisting-reorganisation distortions, and make rows open the shared stock
  detail. Never infer company leaders from the industry-flow ranking or fill provider failures with samples.
- Portfolio and watch quotes are grouped by provider: all A-share codes use one Tencent batch and HK/US
  codes use the existing bounded parallel Yahoo batch; resolve each currency FX once. Do not reintroduce a
  per-row external request loop. Global indices and proxy rotation also use bounded parallel snapshots.
- Independent daily-review modules run concurrently, while calls sharing the Eastmoney session/rate gate
  remain serial inside one worker. Intel symbol modules use bounded workers with independent provider
  sessions; provider rate limits and per-symbol errors remain visible.
- Read-heavy HTTP routes use an in-process response cache with stale-while-revalidate. A stale response must
  set cache metadata and a warning, refresh in the background, and be replaced by the browser's bounded
  polling. `refresh=1`/CLI `--refresh` bypasses both response and provider-fresh caches but still permits
  explicit stale-on-error fallback.
- The browser may keep at most eight successful page snapshots for 30 minutes in local storage so reloads
  render immediately. Snapshots are display accelerators only: live APIs remain authoritative, metadata says
  `browser-local`, and secrets/research writes are never stored there.
- AI capability probing never blocks the current page request. ECharts is loaded only when the financial
  chart is opened; portfolio, watch, daily and intel pages must not eagerly parse the chart bundle.
- Existing `/api/data`, `/chart`, and `/charts/*` remain compatible. `STJ_DASHBOARD_V2=0` restores the
  legacy homepage.
- Runtime keys: `STJ_WORKSPACE`, `STJ_DB`, `STJ_DASHBOARD_V2`, `STJ_API_KEY`, `STJ_PUBLIC_MODE`,
  `STJ_PYTHON`, `STJ_DATA_TIMEOUT_MS`, `STJ_QUOTE_TTL_SECONDS`, `STJ_RENDER_CHART`,
  `STJ_QUOTE_TIMEOUT_MS`, `HOST`, `PORT`.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Invalid `ts_code`, enum, length, or sector URL | HTTP/CLI `400`, stable public error code |
| JSON body too large/invalid | `413 BODY_TOO_LARGE` / `400 INVALID_JSON` |
| Non-JSON or cross-origin write | `415 UNSUPPORTED_MEDIA_TYPE` / `403 ORIGIN_REJECTED` |
| Missing/wrong `STJ_API_KEY` | `401 UNAUTHORIZED`; non-loopback cannot start without a key |
| Provider timeout/403/429/bad schema | Classified provider error; independent section failure |
| Expired cache plus provider failure | Return explicit `cache.stale=true` and warning |
| Stale response snapshot | Render immediately, label the age/layer, start one deduplicated background refresh |
| Explicit refresh | Wait for a provider refresh; do not return the normal fresh response-cache hit |
| HK/US same-basis individual flow unavailable | Capability `available=false`; never substitute performance |
| A-share breadth unavailable | Explicit proxy/unknown basis; never derive temperature from top industry flows |
| AI accepted but first token not ready | Animated processing state remains visible and stop stays available |
| CLI provider/model mismatch | Reject the request; never silently launch another CLI runtime |
| Unsafe AI Base URL, credentials, private/metadata IP or redirect | `SSRF_BLOCKED`/`INVALID_BASE_URL` |
| AI secret | Only request body/header/stdin; never argv, log, cache, DB, fixture, or research record |
| Unsupported tool/too many rounds | Reject allowlist violation; cap at six rounds |

### 5. Good / Base / Bad Cases

- Good: A/HK/US symbol returns normalized asset, source time and available modules; one failed module
  appears in `errors` while the rest render.
- Base: missing optional financial/flow/options data returns `null` or an unavailable capability and the
  UI explains why.
- Bad: fabricating a company description, calling arbitrary SQL/shell/URL from an AI tool, silently using
  stale data, or labeling HK/US ETF performance as net fund flow.

### 6. Tests Required

- Unit: normalization/nulls, provider classifications, cache fresh/stale/corrupt, financial periods,
  capability downgrades, index exchange prefixes, two-sided industry flow, real/proxy market temperature,
  normalized market leaders and listing-day exclusion, provider quote batching, parallel index/intel fetch,
  response-cache SWR, AI catalog/context/SSRF/tool loop, CLI runtime mapping/stream parsing, sector validation
  and migration idempotency.
- Integration: Node shell/assets/API, sector create-update-archive-restore, research save/list/delete/clear,
  optional auth, legacy flag and `/api/data`, OpenAI-compatible NDJSON stream with no secret echo.
- Regression: original `stock-chart.html` retains curve/K-line, zoom, B/S/T, `记`, mark lines,
  `交易标注` and `关注记录`, with no second record source.
- Release: real A/HK/US read-only smoke after a `0600` SQLite backup; compare core-table counts before/after.

### 7. Wrong vs Correct

#### Wrong

```python
# Browser-supplied facts and silent substitution are not trusted contracts.
context = request["portfolio"]
flow = etf_change_pct
```

#### Correct

```python
# Accept a descriptor, reload trusted facts, and state capability boundaries.
descriptor = normalize_descriptor(request.get("context"))
context = build_context(DashboardService(workspace), descriptor)
flow = {"capability": {"available": False, "reason": "no same-basis source"}}
```
