# 数据接入盘点与来源矩阵

## 1. 盘点结论

- 当前真实数据包含 9 个持仓（A/港/美 = 3/2/4）和 9 个关注（A/港/美 = 4/3/2），不能按单一市场设计。
- 组合权重、同公司跨市场暴露和本地笔记已经由 `quote_adapter.py`、`evidence_pack.py` 与 `db_schema.py` 提供，应复用而非再算一套。
- `a-stock-data` 与 `global-stock-data` 是实现参考，不应成为运行时 sibling 依赖；只移植本任务需要的函数、来源切换、限流和错误处理。
- A 股可获得真实板块主力净流入；港美没有同等可靠的统一口径时，只展示行业/ETF 表现代理，并明确 `metric_kind=performance_proxy`。
- “AI 数据工具”是模型可调用的只读结构化查询函数，不是新的 AI 模型或数据供应商。CLI 模式不调用工具，而是预先加载同一份结构化上下文。

## 2. 本地事实源

| 能力 | 现有入口 | 复用方式 | 数据性质 |
| --- | --- | --- | --- |
| 持仓、成本、盈亏 | `db_schema.py` / `query_positions.py` | 通过现有 accessor 读取 | 本地权威 |
| 交易记录 | `db_schema.py` / `query_trades.py` | 按 `ts_code` 读取 | 本地权威 |
| 关注列表、目标/止损 | `db_schema.py` / `watchlist.py` | 通过现有 accessor 读取 | 本地权威 |
| 统一笔记 | `db_schema.py` / `notes.py` | 读取三类 note；不恢复旧记录栏 | 本地权威 |
| 跨市场报价与汇率 | `quote_adapter.py` | 扩展 provider，不复制代码映射 | 外部快照 |
| 人民币权重与同公司暴露 | `evidence_pack.py` | 作为 portfolio context 唯一算法入口 | 派生数据 |
| K 线与标注 | `render_chart.py` + `stock-chart.html` | 保持既有路由和交互契约 | 本地+外部 |

## 3. 外部数据来源矩阵

| 数据域 | A 股首选 / 备选 | 港股首选 / 备选 | 美股首选 / 备选 | 默认缓存 | 首期 |
| --- | --- | --- | --- | --- | --- |
| 实时报价 | 现有东财 / 腾讯 | 现有 Yahoo / 腾讯、Sina | 现有 Yahoo / Sina、腾讯 | 30–60 秒 | M1 |
| K 线 | 保留现有东财 | 保留现有 Yahoo | 保留现有 Yahoo | 按现有图表缓存 | M2 |
| 公司业务 | F10/公开公司资料 | Yahoo/公司资料 | Yahoo/SEC company facts | 7 天 | M3 |
| 估值 | 东财估值与历史分位 | Yahoo/东财可得字段 | Yahoo/东财可得字段 | 15 分钟 | M3 |
| 财务三表/指标 | Sina/东财公开财务接口 | Yahoo/东财 | SEC XBRL / Yahoo | 12–24 小时 | M3 |
| 个股资金面 | 东财资金流、两融、龙虎榜等 | 有可靠字段才展示 | 有可靠字段才展示 | 5–15 分钟 | M3/M6 |
| 个股新闻 | 财经新闻接口，保留原文链接 | Yahoo/财经新闻 | Yahoo/财经新闻 | 15 分钟 | M4 |
| 研报 | 东财/公开研报索引 | 可得研报索引 | 可得分析师/研报索引 | 6 小时 | M4 |
| 公告/监管 | CNInfo/交易所 | HKEX/公开披露 | SEC EDGAR | 24 小时 | M6 |
| 大盘指数 | A 股指数接口 | 港股指数接口 | 全球指数接口 | 60 秒 | M4 |
| 市场温度 | 涨跌停/广度等公开指标 | 涨跌家数/指数代理 | 涨跌家数/指数代理 | 5 分钟 | M4 |
| 板块轮动 | 东财真实主力净流入 | 行业/ETF 表现代理 | 行业/ETF 表现代理 | 开盘 5 分钟，收盘 30 分钟 | M4 |
| 期权 | ETF 期权（标的适配时） | 暂不承诺 | Yahoo 期权链 | 5 分钟 | M6 |
| Investment News | 跨市场宏观、政策、行业新闻 | 同左 | 同左 | 15 分钟 | M4 |

来源顺序是设计默认值，实施时每个端点必须用 fixture 验证字段与可用性；未验证的备选源不得静默上线。

## 4. 限流与依赖结论

- 所有东财请求统一经过共享客户端：串行、最小间隔 1 秒、附加 0.1–0.5 秒抖动；429/5xx 有界重试，403 不盲目重试。
- Yahoo 相关函数共享 crumb/cookie 管理与 User-Agent；不得让各端点各自实现登录态。
- 首批必需新增依赖仅为 `requests`。现有图表链路已覆盖 K 线，不因本任务强制引入 pandas/stockstats。
- `mootdx` 只在 A 股 F10 数据验证确有必要时作为可选依赖；无它时要有清晰降级，不影响持仓、K 线和 AI 基础上下文。
- 外部 API 结果写原子 JSON 缓存到 `~/.trade-journal/results/trade-journal/cache/dashboard/`，不写入业务 SQLite。

## 5. 缺失值与口径

- 缺失数字一律为 `null`，不能用 0 冒充。
- 原始行情和财务保留标的币种；只有组合汇总与权重使用人民币估算，并带汇率时间。
- 统一标的键为 `ts_code`，另存 `market_group`（A/HK/US）、`exchange` 与 `currency`。
- 财务期使用 FY/Q/TTM 明确标识，不能混画；图表必须标出报告期和来源日期。
- 每条新闻/研报/公告保留 `source_name`、`source_url`、`published_at`、`fetched_at`。
- 过期缓存回退必须返回 `stale=true` 与警告；所有来源都失败时展示可恢复错误，不渲染伪数据。
