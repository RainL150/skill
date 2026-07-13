# 实现边界与复用清单

## 1. 保留不变的能力

- `live_server.mjs` 继续是唯一 HTTP 入口，默认只监听 loopback，保持零构建启动方式。
- `/chart?code=&period=`、`/charts/*` 与 `/api/data` 保持兼容。
- `render_chart.py` 与 `templates/stock-chart.html` 是 K 线体验基线：曲线/K线、缩放、十字提示、B/S/T、“记”、四类价位线、统计胶囊、图下交易标注与关注记录都保留。
- 交易、持仓、关注、笔记的读取和写入继续经过 `db_schema.py` accessor。
- `parse_ts_code`、报价标准化、人民币组合权重、同公司暴露都只能有一个实现。

## 2. 从 Vibe 参考实现移植的能力

### AI 配置

- 订阅 CLI：Claude Code、Qwen Code、DeepSeek CLI、Codex；OpenCode、Cursor Agent、Kimi 只显示“即将支持”。
- API 预设：DeepSeek V4 Flash/Pro、SiliconFlow DeepSeek V3、OpenAI GPT-4o、MiniMax M2、豆包 Pro、OpenRouter GPT-4o、Groq Llama 3.3、Together Llama、MiMo、自定义 OpenAI-compatible。
- 一次只有一个当前配置；Base URL、Model、API Key 存浏览器 `localStorage`，后端不持久化。
- API 使用流式 chat completions + function calling；CLI 使用本机登录态和流式 stdout，但只消费预装上下文。
- 移植 CLI 可用性检测、进程取消、流式解析、工具调用循环与 SSRF 防护；不引入 Vibe 的 FastAPI/React 运行时。

### 数据函数

- 从 `a-stock-data` 选择性移植公司资料、估值、财务、资金、研报、新闻、公告、指数与 A 股轮动函数。
- 从 `global-stock-data` 选择性移植港美公司资料、财务、Yahoo 分析师/期权与 SEC 文件函数。
- 数据函数必须包进 STJ 的标准响应、缓存、限流和错误模型，不能直接把上游不稳定字段透给页面。
- 外部参考目录只用于开发对照，交付后的 `stock-trade-journal` 必须 self-contained。

## 3. 新增能力

- Dashboard SSR 壳、左侧导航、Alpine 局部状态与响应式样式。
- 统一跨市场查询 CLI、provider adapter、原子缓存与来源元数据。
- 板块知识、产业链节点/边、标的映射与研究记录的 SQLite 表及 CRUD accessor。
- 全局 Ask AI 抽屉、页面上下文组装、NDJSON 流、工具轨迹与研究记录保存。
- 本地/外部数据的契约测试、provider fixture、Node 路由测试与端到端 smoke。

## 4. AI 数据工具定义

这些工具只读、参数受控，返回规范化 JSON；模型不能传任意 URL、SQL 或 shell 命令。

| 工具 | 作用 | 数据边界 |
| --- | --- | --- |
| `stj_get_portfolio_context` | 当前持仓、关注、权重、盈亏和提醒 | 本地 DB + 归一化报价 |
| `stj_get_symbol_context` | 单标的交易、持仓、关注、笔记摘要 | 本地 DB |
| `market_get_quote` | A/港/美报价 | provider 层 |
| `market_get_company_profile` | 公司主营与关键业务变量 | provider 层 |
| `market_get_valuation` | 当前估值和历史分位 | provider 层 |
| `market_get_financials` | 标准化财报序列和质量指标 | provider 层 |
| `market_get_news` | 个股或 Investment News | provider 层，限制条数 |
| `market_get_reports` | 个股研报/分析师材料 | provider 层，限制条数 |
| `market_get_sector_context` | 板块标签、产业链和核心知识 | 本地 DB |

工具结果设条数、字节和轮次上限；UI 显示工具名、来源、耗时与错误，但不显示 API Key 或内部命令行。

## 5. 存储边界

- 既有表不改语义；新增表由 `db_schema.py` 独占创建与迁移。
- 新增：`sectors`、`sector_tags`、`sector_nodes`、`sector_edges`、`sector_symbols`、`sector_knowledge`、`research_records`。
- 产业链 stage 枚举为 upstream/midstream/downstream；知识 kind 使用集中常量校验。
- `research_records` 保存问题、答案、引用与页面上下文摘要，不保存 API Key、完整请求头或模型原始密钥配置。
- provider 缓存是可删除的派生数据，不进入 SQLite，也不参与备份恢复承诺。

## 6. 明确不做

- 不重建 Vibe 的 React + FastAPI 技术栈。
- 不复制全部 A 股/全球数据 skill；只接本看板与 AI 工具实际消费的数据。
- 不提供自动交易、下单、自动修改持仓或让 AI 写任意数据库。
- 不把港美行业表现命名成真实资金净流入。
- 不在首版实现多模型并行回答、云端同步 AI Key、用户系统或公网多租户。
- 不删除现有 K 线页面和旧 API；兼容层至少保留一个发布周期。
