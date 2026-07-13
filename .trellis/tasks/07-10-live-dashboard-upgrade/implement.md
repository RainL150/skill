# Implementation Plan — STJ 跨市场投资数据看板与全局问 AI

## Implementation Result — 2026-07-10

实现已完成并通过自动化与真实只读联调：

- 新版投研工作台默认启用，`STJ_DASHBOARD_V2=0`、`/api/data`、`/chart`、`/charts/*` 兼容路径保留。
- 真实工作区迁移前创建了 `0600` SQLite 备份；迁移前后 `trades=25`、`positions=12`、`watchlist=9`、`notes=37`，`PRAGMA integrity_check=ok`。
- A/港/美真实标的概览与财报通过；A 股资金面可用，港美明确 capability 降级；美股期权、个股资讯、组合雷达与三市场复盘通过。
- Claude Code CLI 完成真实 `meta → delta → done` 流式 smoke；OpenAI-compatible 使用本地兼容端点完成 Node→Python→SSE→NDJSON 端到端测试和密钥不回显断言。
- 21 个 Python 单元测试、6 个 Node 集成测试、Python/Node 语法、skill validator、Trellis validator、secret/CDN scan、`git diff --check` 全部通过。
- `stock-trade-journal/references/dashboard-guide.md` 记录启动、数据边界、完整 AI 目录、只读数据工具、备份恢复和验收流程；`.trellis/spec/scripts/dashboard.md` 固化跨层契约。

环境限制与显式降级：

- 当前执行环境没有可用的内置浏览器，无法完成截图式桌面/窄屏人工验收；已改用 HTML/JS 语法、HTTP 壳、API 和契约测试，仍需在有浏览器的环境做最终视觉复验。
- 本机 Codex CLI 被工作区外两份缺少 YAML frontmatter 的 skill 配置拦截；STJ 能正确返回结构化错误，Claude Code CLI 路径已真实通过。未修改这些外部 skill。
- 没有使用用户的商业 API Key；真实供应商 API 的协议路径由本地 OpenAI-compatible 端点端到端覆盖。
- 市场节假日日历尚未接入，交易状态明确显示“常规时段估算”；港美真实个股净资金流继续 fail closed。

## Follow-up Result — 2026-07-11（Vibe 问 AI 完整度补齐）

- 补入 Vibe 的五维个股分析框架，并增加板块七维框架、结论/关键数据/表格/风险/数据缺口输出纪律。
- 设置页补齐 CLI/API 接入卡片、11 个 API 预设与自定义端点、当前连接快速试问、能力对比、独立后端密钥、来源与保存开关。
- 全局抽屉补齐可信上下文预览、页面级建议问题、停止/关闭中止、失败重试、工具参数/条数/截断/来源和显式保存。
- 每日复盘增加页内“AI 当日复盘”；资讯雷达增加当前筛选提炼及持仓/关注/Investment News 顺序批量提炼。
- 左侧增加研究记录页，支持展开来源、回到标的/板块、单条删除和确认清空；新增对应 CLI/HTTP 删除契约。
- 自动化通过：24 个 Python 单元测试、7 个 Node 集成测试、JS/Python 语法检查。真实内置浏览器验收通过设置、多模型列表（11 项）、全局抽屉、页内复盘/资讯和研究记录空态；验收中修复了从个股问 AI 进入设置时详情抽屉残留，以及未配置状态的 Alpine 空引用。

## Follow-up Result — 2026-07-12（AI 流显示与市场宽度纠偏）

- 修复聊天回复已在后端生成但抽屉仍为空白：流事件现在按消息 id 回查并更新 Alpine 响应式对象；首个片段前显示动态处理状态，生成中保留停止入口和流式光标。
- Claude Code 改用 partial `stream-json`，过滤最终重复 payload；服务端严格校验 provider/model，`meta` 和每条消息展示实际 runtime，避免 Claude/Codex 身份看似串线。
- 修复 A 股指数交易所前缀：上证指数固定请求 `sh000001`，不再错误命中 `sz000001` 平安银行。
- 市场温度改为独立的真实市场宽度：乐咕乐股上涨/平盘/下跌家数驱动机械分类，页面同时展示样本量、正向占比、平衡度、来源和时间；不可用时必须显式代理，禁止用精选行业流向代替。
- A 股行业资金流同时取得净流入与净流出两端，条形相对当前最大绝对值缩放，并用中轴表达方向，不再出现所有条同长的装饰性结果。
- 市场宽度卡利用原空白区域加入 6 家真实领涨公司，展示代码、行业、现价、涨幅、换手率、来源与时间；排除上市初期和退市整理标的，点击复用统一个股详情。
- 自动化回归覆盖响应式流协议相关静态契约、Claude partial parser/CLI 映射、指数前缀、双向行业流和真/代理市场温度；真实 Claude Code 浏览器 smoke 收到并展示 `CLAUDE_UI_OK`，等待态与最终正文均可见，控制台无错误。

## Follow-up Result — 2026-07-13（Vibe 级加载体感优化）

- 性能基线确认瓶颈在数据冷路径而非 HTML：页面壳约 1ms，持仓冷/热 9.34s/0.09s，每日复盘冷/热 21.61s/0.08s。
- 持仓/关注改为 A 股单次腾讯批量、港美复用 `quote_many` 有界并发和单币种汇率；报价默认 TTL 从 45 秒调整为 180 秒，并保留逐标的 stale-on-error。
- 全球指数、港美代理轮动改为并行快照；每日复盘独立来源并发，东方财富共享 session/rate gate 的调用仍在单 worker 内串行；资讯雷达标的用独立 provider session 有界并发。
- Node 为只读重接口加入内存 stale-while-revalidate、并发去重和 `refresh=1` 强制更新；浏览器最多保存 8 份、30 分钟成功快照并自动轮询替换后台结果。
- AI capability probe 不再阻塞当前页；ECharts 从全站首屏移除，仅打开财报图时动态加载。CLI 增加统一 `--refresh`，`STJ_QUOTE_TTL_SECONDS` 可调。
- 重启后真实 HTTP：持仓首开 4.23s、内存命中 1.4ms、过期快照先返回 3.9ms、强制更新 4.93s；每日复盘首开 7.54s、内存命中 0.9ms、强制更新在当次网络下 11.50s。浏览器持仓重载 52ms 即有 9 行，资讯雷达首聚合 2.93s/33 条、重载快照 73ms；财报前无 ECharts，打开财报后动态脚本与 canvas 均出现。

## 0. Activation Gate

本文件是执行计划，不代表已授权开发。

- [ ] 用户审阅 `prd.md`、`design.md`、本文件和原型，确认范围与阶段顺序。
- [ ] 确认工作区无与本任务冲突的未提交修改；不得覆盖用户现有变更。
- [ ] 审阅通过后再运行：`python3 .trellis/scripts/task.py start 07-10-live-dashboard-upgrade`。
- [ ] 开发过程按 M0→M7 顺序推进；每个 milestone 的 exit gate 通过后才能进入下一阶段。

## 1. Milestone Map

| Milestone | Deliverable | Depends on | Review gate |
| --- | --- | --- | --- |
| M0 | 基线、fixtures、feature flag、数据安全准备 | none | 旧功能基线可重复 |
| M1 | 统一数据契约、缓存、provider 与 dashboard CLI | M0 | A/港/美离线契约 + 少量 live smoke |
| M2 | 新页面壳、持仓/关注、STJ K 线兼容 | M1 | 核心驾驶舱可用且旧路由不退化 |
| M3 | 个股业务、估值、财报、资金/期权 capability | M2 | A/港/美详情验收 |
| M4 | 资讯雷达与每日复盘 | M1, M2 | 来源/时间/轮动口径验收 |
| M5 | 板块知识与研究记录存储 | M2 | CRUD/迁移/产业链闭环 |
| M6 | Vibe 多供应商 AI、数据工具与全局抽屉 | M1–M5 | CLI + API 双路径验收 |
| M7 | 故障演练、可访问性、文档、总验收 | M0–M6 | 全量门禁通过 |

M3 与 M4 代码上可在 M2 后并行思考，但同一工作区按表中顺序落地与验收，减少 provider/schema 同时漂移。

## 2. M0 — Baseline and Safety Net

### Build

- [ ] 记录当前 `/api/data` 正常响应 fixture，脱敏后放入 `stock-trade-journal/tests/fixtures/legacy/`。
- [ ] 为原 STJ K 线准备 A/港/美各一组 OHLC + 交易/关注/笔记 fixture，并记录关键 marker/价位线断言。
- [ ] 用匿名化数据库副本记录 trades/positions/watchlist/notes 行数和典型查询结果。
- [ ] 增加 `STJ_DASHBOARD_V2` 分支：开发期间默认旧首页，新壳可显式启用；不改变 `/chart`。
- [ ] 确认依赖策略：在 `requirements.txt` 增加 `requests`；只有 provider 验证要求时才把 `mootdx` 设为可选。
- [ ] 写数据库备份/恢复说明，所有 migration 测试只对临时库或副本执行。

### Validate

```bash
python3 stock-trade-journal/scripts/query_positions.py --json
python3 stock-trade-journal/scripts/watchlist.py ls --json
python3 stock-trade-journal/scripts/render_chart.py RDDT.US --period 1y --no-latest
PORT=8877 STJ_DASHBOARD_V2=0 node stock-trade-journal/scripts/live_server.mjs
```

### Exit / rollback

- [ ] 基线 fixture 可离线重放；旧首页、旧 JSON 和 K 线 smoke 通过。
- [ ] 若现有行为不能稳定重放，先补基线测试，不进入 M1。
- [ ] 本阶段回滚只删除新增 test/flag；不触碰用户数据库。

## 3. M1 — Data Foundation

### M1.1 Contracts, cache and CLI

- [ ] 创建 `scripts/dashboard/` 包与 `dashboard_data.py` argparse 入口；所有子命令支持 `--help`、`--workspace` 和 JSON 输出。
- [ ] 实现标准 envelope、稳定错误码、AssetRef/Quote/Financial/Intel/Rotation normalization。
- [ ] 实现原子 JSON cache、contract version、TTL、stale-if-error、corruption quarantine 与 0600 权限。
- [ ] 实现 provider base、timeout、响应大小限制、schema error 与 fallback orchestration。
- [ ] 实现东财跨进程 rate gate；所有东财函数只能经 shared client。
- [ ] 复用 `parse_ts_code`、`quote_adapter.py` 与 `evidence_pack.py`，删除/禁止新增重复市场映射和权重算法。

### M1.2 A/HK/US providers

- [ ] 从 A 股参考能力选择性移植报价补充、公司资料、估值、财务、资金、新闻/研报、指数与轮动函数；保留限流与来源元数据。
- [ ] 从全球参考能力选择性移植港美公司资料、财务、Yahoo session、分析师/期权与 SEC 函数。
- [ ] 每个端点先用保存的响应 fixture 写 parser test，再接 service；不得先连 UI 后补字段定义。
- [ ] 对每个自动 fallback 记录“首选失败→备选成功”和“全部失败→stale/错误”fixture。
- [ ] 实现 `portfolio`、`watchlist`、`stock-context`、`stock-financials`、`stock-flow`、`stock-intel`、`stock-options`、`daily-review`、`intel` 子命令。
- [ ] `stock-options` 与非适用资金数据返回 capability 状态，而不是空数组冒充成功。

### Test

- [ ] A/港/美各覆盖：正常、null、坏 schema、timeout、429/403、stale cache。
- [ ] 验证财务 FY/Q/TTM 不混合，FCF 计算带组成字段，币种不丢失。
- [ ] 验证 rotation 的 A 股为 `net_flow`，港美代理为 `performance_proxy`。
- [ ] 并发启动多个 provider 测试，确认东财请求间隔跨进程生效。
- [ ] 搜索缓存、日志和 fixture，确认无 key/token/Authorization。

```bash
python3 -m unittest discover -s stock-trade-journal/tests -p 'test_dashboard_*.py'
python3 stock-trade-journal/scripts/dashboard_data.py --help
python3 stock-trade-journal/scripts/dashboard_data.py portfolio --json
```

### Exit / rollback

- [ ] 默认离线测试全部通过；显式 live smoke 用 A/港/美各一只标的通过并记录时间/来源。
- [ ] 数据 CLI 可独立于页面使用，外部参考目录移走后仍能运行。
- [ ] provider 不稳定时可在 service capability 中单独关闭，不影响本地组合读取。

## 4. M2 — Shell, Portfolio, Watchlist and K-line

### M2.1 Node and static shell

- [ ] 拆出 `scripts/live/http_helpers.mjs`、`python_bridge.mjs`、`api_routes.mjs`；`live_server.mjs` 保持入口与配置职责。
- [ ] 子进程全部使用 `spawn/execFile` 参数数组和绝对脚本路径；支持 timeout、client abort、stderr 脱敏和退出清理。
- [ ] 增加静态资源 allowlist/realpath 校验、JSON body limit、method/origin/content-type 校验和 HTTP status mapping。
- [ ] vendor Alpine.js 与 license notice；创建 `dashboard.html/css/js`，运行时不请求 CDN。
- [ ] 实现桌面左侧菜单、移动收起、URL route 恢复、页面 loading/empty/partial/stale/error 状态。
- [ ] 注册 `/api/portfolio`、`/api/watchlist` 和兼容 `/api/data`；旧字段保持不变。

### M2.2 Portfolio and watch UI

- [ ] 顶部只展示总市值、总浮盈、今日盈亏、待处理提醒，删除最大权重。
- [ ] 持仓列实现权重与“收益金额 + 收益率”合并；使用统一红/绿/中性/缺失 token 和 `+/-` 文本。
- [ ] 关注表展示目标/止损/距离，持仓和关注共用 `openStockDetail(tsCode)`。
- [ ] 同公司跨市场暴露和汇率时间在不干扰主表的次级信息中可见。

### M2.3 K-line compatibility

- [ ] 详情骨架嵌入现有 `/chart`，保持 period 与标的切换；处理 iframe 高度和错误态。
- [ ] 用 fixture 对照曲线/K线、crosshair、zoom、B/S/T、“记”、四种价位线和统计胶囊。
- [ ] 验证图下只有“交易标注/关注记录”两栏，没有重复“我的记录”。
- [ ] 对现有 `stock-chart.html` 的任何修改先补回归断言，不做风格性重写。

### Validate

```bash
node --check stock-trade-journal/scripts/live_server.mjs
node --test stock-trade-journal/tests/live_server.test.mjs
PORT=8877 STJ_DASHBOARD_V2=1 node stock-trade-journal/scripts/live_server.mjs
```

### Exit / rollback

- [ ] 真实持仓/关注和窄屏人工验收通过；旧 `/api/data`、`/chart`、`/charts/*` 回归通过。
- [ ] `STJ_DASHBOARD_V2=0` 可立即恢复旧首页；M2 问题不要求回滚 M1 数据 CLI。

## 5. M3 — Stock Detail

### Build

- [ ] 实现 `/api/stock/context`：本地事实、报价、关注状态、业务说明、估值摘要和来源。
- [ ] 实现顶部四格持仓/关注状态切换，盈亏金额与比例同组件展示。
- [ ] 概览展示主营、竞争位置、客户/渠道与关键变量；字段不全时按来源降级，不生成伪说明。
- [ ] 实现 `/api/stock/financials` 与财务柱状图：营收、净利润、FCF；年度/季度切换且不混币种。
- [ ] 增加毛利率、现金含量、研发、EPS、资产负债、营运资金、应收、库存等质量卡；只显示实际可得项。
- [ ] 实现 `/api/stock/flow` 与 capability-aware UI；A 股资金、两融、龙虎榜等分来源展示。
- [ ] 实现 `/api/stock/options`；首版验证美股/Yahoo 和适配 A 股 ETF，港股明确不承诺。
- [ ] 实现 `/api/stock/intel`，把新闻、研报、公告合为一个 tab 和统一筛选。

### Test and acceptance

- [ ] A/港/美各一只真实标的走完概览、K线、财报、资讯；A/美另验资金或期权，港股验 capability 降级。
- [ ] 关注但未持仓标的不出现虚假数量、成本或浮盈。
- [ ] 财务缺字段、不同币种、不同报告期和计算 FCF fixture 通过。
- [ ] 新闻/研报/公告外链、来源时间、HTML 转义与去重通过。

### Exit / rollback

- [ ] `STOCK-01..09` 验收完成；单一深数据模块可通过 capability 隐藏，K 线与本地事实始终可用。
- [ ] provider schema 漂移时回退到 stale 或模块错误，不回写本地表。

## 6. M4 — Daily Review and Intelligence Radar

### Daily review

- [ ] 实现 `/api/daily-review?market=A|HK|US`，包含指数、全球市场、市场温度、交易状态和轮动。
- [ ] 时区/交易日逻辑用 fixture 覆盖休市、盘前、盘中、盘后；所有模块显示各自 `as_of`。
- [ ] A 股 `net_flow` 使用资金单位；港美 `performance_proxy` 使用涨跌幅/成交等代理单位和不同标题。
- [ ] 对尚未验证的港美轮动来源 fail closed，不用随机行业榜补位。

### Intelligence radar

- [ ] 实现 `/api/intel`，从持仓和关注生成 universe，再聚合 news/report/filing/investment_news。
- [ ] 实现规范 URL/标题 hash 去重，原始标题与 AI 摘要分离。
- [ ] 排序结合持仓权重、关注优先级、时效、相关度和风险标签；权重公式写成具名函数并测试边界。
- [ ] UI 实现市场、范围、类型筛选和风险突出；每条都能回到原文。

### Exit / rollback

- [ ] `RADAR-01..04`、`REVIEW-01..04` 验收通过。
- [ ] 断网和单源失败时各 section 独立降级；可关闭 Investment News 或单市场轮动而不影响个股详情。

## 7. M5 — Sector Knowledge and Research Records

### Schema and accessors

- [ ] 在 `db_schema.py` 集中定义 sector stage、knowledge kind、research scope 枚举。
- [ ] 新增 `sectors`、`sector_tags`、`sector_nodes`、`sector_edges`、`sector_symbols`、`sector_knowledge`、`research_records` 及索引。
- [ ] 实现参数化 CRUD accessor、短事务、节点删除连带 edge 清理、板块软归档与恢复。
- [ ] migration 在空库和匿名化现有库副本上运行两次，验证幂等；比较既有核心表行数/查询结果。

### API and UI

- [ ] 实现 sector REST routes，统一输入长度、URL、枚举和 ts_code 校验。
- [ ] 完成“新建→标签→摘要/核心知识→上中下游节点/边→关联标的→归档/恢复”页面闭环。
- [ ] 产业链节点可标记 bottleneck，edge 可表达依赖关系；无节点时给引导空态。
- [ ] 板块页固定四个 AI prompt，仅负责打开 Ask AI 并附带 sector id。
- [ ] 实现 `/api/research-records`，保存前 secret redaction；不把聊天自动落库。

### Exit / rollback

- [ ] `SECTOR-01..05` 与 schema 验收通过；既有数据完全不变。
- [ ] 旧代码回滚后只忽略新表；不得用 DROP TABLE 回滚。

## 8. M6 — Full Ask AI Integration

### M6.1 Settings and capability catalog

- [ ] 按 Vibe 基线实现 CLI/API 两模式和完整模型目录；不可用 CLI 与 coming-soon 项状态区分。
- [ ] 按 `research/ai-configuration-matrix.md` 逐项实现并做 snapshot：provider id、model id、默认 Base URL、展示名和 coming-soon 状态不得遗漏。
- [ ] 预设填 Base URL/Model，豆包支持 `ep-…`，自定义支持 OpenAI-compatible 与本地 Ollama。
- [ ] 使用 `stj.ai.config.v1` 保存唯一当前配置；实现清除配置、默认上下文和回答结构设置。
- [ ] 实现 `/api/ai/capabilities` 的 binary probe 与状态，不返回路径中的敏感信息或登录 token。

### M6.2 Runtime and stream

- [ ] 实现 `dashboard_chat.py` stdin JSON / stdout NDJSON；定义 meta/delta/tool_start/tool_result/done/error。
- [ ] 移植并验证 Claude Code、Qwen Code、DeepSeek CLI、Codex 的固定命令模板、登录/不可用检测、流解析与取消。
- [ ] 实现 OpenAI-compatible streaming；不支持 tool calling 时显式降级到预装 context。
- [ ] 实现 context builder：页面 descriptor 只允许服务端重取受信数据，不能由浏览器伪造整份事实 payload。
- [ ] 实现工具：portfolio context、symbol context、quote、profile、valuation、financials、news、reports、sector context。
- [ ] 限制工具最多 6 轮、单次 20 条、注入模型默认 6,000 字符、内部 payload 50KB，并限制总上下文预算；显示截断与来源。

### M6.3 Security and UI

- [ ] API Key/后端 key 只通过 request body/header 和 stdin；确保不出现在 argv、log、cache、DB、fixture、error。
- [ ] 实现 Base URL scheme/credentials/DNS/IP/redirect 校验；loopback 与非 loopback 模式分别测试。
- [ ] 非 loopback 启动强制 `STJ_API_KEY`；loopback 可选。
- [ ] 所有一级页和详情接入统一 AI 抽屉：多轮、建议问题、stream、stop、retry、tool trace、来源和保存研究记录。
- [ ] CLI 路径验证“预装上下文、无工具”；API 路径验证 function calling 和工具错误恢复。

### Test matrix

| Case | CLI | API |
| --- | --- | --- |
| 正常流式 | 至少 1 个已安装 CLI | 至少 1 个兼容端点 |
| 多轮历史 | yes | yes |
| 中途停止 | child terminated | HTTP/child aborted |
| 无登录/401 | 独立错误 | 独立错误 |
| timeout/rate limit | 可重试提示 | 可重试提示 |
| 数据工具 | 预装 context、0 调用 | 调用、轨迹、来源 |
| secret scan | argv/log/cache/DB 无密钥 | 同左 |
| SSRF | 不适用 | metadata/private/redirect cases |

### Exit / rollback

- [ ] `AI-01..10` 完整验收，不能只用 mock 冒充 CLI/API 可用。
- [ ] `/api/chat` 可独立 feature-disable；关闭 AI 后所有数据页正常。
- [ ] 遇到兼容端点 tool schema 差异时降级无工具，不放宽任意 URL/命令权限。

## 9. M7 — Hardening, Documentation and Release

### Full validation

```bash
python3 -m unittest discover -s stock-trade-journal/tests -p 'test_*.py'
node --test stock-trade-journal/tests/*.test.mjs
node --check stock-trade-journal/scripts/live_server.mjs
python3 skill-evolution-loop/scripts/validate_skill.py stock-trade-journal
python3 .trellis/scripts/task.py validate 07-10-live-dashboard-upgrade
```

- [ ] 在缓存冷/热、断网、provider 部分失败、全失败、坏缓存、休市、并发请求下完成故障演练。
- [ ] 桌面/窄屏完成导航、表格、详情、图表、表单、键盘焦点、颜色+符号验收。
- [ ] 默认运行路径无 CDN、无 Vibe/sibling skill 依赖；临时移走参考目录再运行 smoke。
- [ ] 搜索 secret、高风险 URL、shell spawn、直接 SQL 和重复 symbol mapping。
- [ ] 更新 `README.md`、`SKILL.md`：启动、依赖、AI 模式、数据来源、缓存、隐私、降级和故障排查。
- [ ] 把 live smoke 的标的、时间、来源、结果写入任务验证记录，但不提交用户持仓或密钥。
- [ ] 完成 PRD requirement trace：NAV/PORT/STOCK/RADAR/REVIEW/SECTOR/AI/DATA/NFR 每项有测试或人工证据。

### Release gate

- [ ] 所有自动门禁和人工验收通过后，把 `STJ_DASHBOARD_V2` 默认值切为 1；保留显式 0 回滚。
- [ ] 对真实 DB 做升级前备份，再运行一次幂等迁移和只读对账。
- [ ] 按 Trellis 完成 check、spec update、commit 和 finish 流程；未通过项不得用“已知问题”静默放行。

## 10. Review Checkpoints

1. **M1 data review**：字段口径、来源、限流、缓存和缺失/过期行为。
2. **M2 UX compatibility review**：左侧框架、持仓/关注、原 STJ K 线逐项对照。
3. **M4 research workflow review**：个股详情、资讯雷达和每日复盘口径是否够用且不误导。
4. **M5 persistence review**：板块模型、迁移和研究记录是否符合长期维护。
5. **M6 AI security review**：模型清单、CLI/API 能力、工具只读、密钥与 SSRF。
6. **M7 release review**：全量 acceptance、回滚与文档。

## 11. Definition of Done

- [ ] `prd.md` 的全部 acceptance 有可追溯证据。
- [ ] 新旧 API、数据库迁移、K 线和 AI security 无未解决高风险问题。
- [ ] 默认测试全离线、稳定可重复；live smoke 是补充而非唯一证据。
- [ ] 运行产物 self-contained，用户无需安装 Vibe 或其他 sibling skill。
- [ ] 回滚只需环境开关/旧代码，不删除数据库表、不丢失研究记录或交易数据。
- [ ] Trellis validation、skill validator、Python/Node tests 和人工三市场验收全部通过。
