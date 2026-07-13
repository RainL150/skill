# STJ 投研工作台指南

## 启动

在 skill 根目录执行：

```bash
python3 -m pip install -r requirements.txt
PORT=8787 node scripts/live_server.mjs
```

浏览器打开 `http://127.0.0.1:8787/`。默认首页是新版投研工作台；临时设置
`STJ_DASHBOARD_V2=0` 可恢复旧首页，`/api/data`、`/chart` 和 `/charts/*` 始终保留。

工作台包含固定左侧菜单、持仓、关注、每日复盘、资讯雷达、板块知识、研究记录、问 AI 设置，
以及所有页面共用的问 AI 抽屉。持仓和关注行都会打开同一套个股详情。

## 数据与能力边界

- 本地事实来自 `~/.trade-journal/results/trade-journal/db/trades.db`。
- A 股行情、资金、研报和公告主要来自腾讯财经/东方财富；港美行情、公司资料、财报、新闻、分析师动态和期权主要来自 Yahoo Finance。
- 所有外部模块都返回来源、数据时间、缓存状态、警告和独立错误；缓存损坏会隔离，实时来源失败时才显式回退旧缓存。
- A 股“市场宽度”单独使用乐咕乐股公开市场活跃度中的上涨/平盘/下跌家数，展示样本量、正向占比、
  多空平衡度、来源和数据时间；不能从行业资金流榜单推导市场温度。来源不可用时页面会明确标为代理或未知，
  不会把替代值冒充全市场宽度。
- 市场宽度卡片下方展示东方财富沪深 A 股涨幅榜中的 6 家领涨公司，包含代码、行业、现价、涨幅、换手率和
  数据时间，点击可直接打开统一个股详情。榜单排除上市初期和退市整理标的，来源失败时显示不可用，不放演示公司。
- A 股行业轮动使用东方财富主力净流入，同时取流入与流出两端；条形以当前列表最大绝对值为尺度，
  中轴左右分别表示流出/流入，不再用固定宽度装饰。港美显示行业/ETF 表现代理，不能解释成净资金流。
- 港美个股资金流没有可靠同口径来源时明确显示不可用；期权按 Yahoo 实际返回能力显示。
- 市场交易状态暂按工作日和常规时段估算，页面会标注“常规时段估算”，不冒充交易所节假日日历。
- 个股 K 线直接复用原 STJ `/chart`：曲线/K线、缩放、B/S/T、“记”、现价/成本/目标/止损线，以及图下交易标注和关注记录均沿用同一数据源，不另建“我的记录”。

缓存位于 `~/.trade-journal/results/trade-journal/cache/dashboard/`，文件权限为 `0600`。
缓存和页面运行时不依赖 Vibe 或其他 sibling skill，也不请求前端 CDN。

## 页面加载与刷新

- 持仓与关注会把 A 股合成一次腾讯请求，港美使用最多 4 个并发的 Yahoo 行情请求，并按币种只取一次汇率；
  默认报价 TTL 为 180 秒，可用 `STJ_QUOTE_TTL_SECONDS` 调整。
- 每日复盘的全球指数、A 股指数、市场宽度和市场模块并发加载；资讯雷达对标的使用有界并发，不会再逐只串行等待。
- Node 对持仓、关注、复盘、资讯和详情保留内存响应快照。新鲜期过后先返回上次结果并明确标为缓存，同时后台刷新；
  浏览器每 2.5 秒轻量检查一次，拿到新结果后自动替换。
- 浏览器最多保存 8 份、30 分钟内的成功页面快照，刷新或新标签打开时可立即铺出内容；快照只含页面返回数据，
  不含 AI/API Key，并以 `browser-local` 标记，实时接口仍是事实来源。
- AI CLI 能力探测在后台运行，不阻塞当前页面；1.1MB ECharts 只在打开个股“财报”图表时按需加载。
- 顶部“刷新”会请求 `refresh=1`，等待真实 provider 更新；CLI 可附加 `--refresh` 获得同样行为。

## 问 AI 配置

AI 配置只保存在当前浏览器的 `localStorage`，键名是 `stj.ai.config.v1`；同一时间只有一个当前配置。
可选的 STJ 后端访问密钥使用独立键 `stj.backend.access_key.v1`，清除 AI 配置不会清掉后端密钥。

订阅 CLI：

- 已接入：Claude Code、Qwen Code、DeepSeek CLI、Codex。
- 展示但不可选：OpenCode、Cursor Agent、Kimi（即将支持）。
- 后端会检测本机二进制。CLI 在隔离临时目录中运行，由服务端预装可信页面上下文，不开放数据工具。
- Claude Code 使用 partial `stream-json` 输出；Codex 使用 Codex 自己的运行入口，两者按 provider/model
  精确校验，不会互相代跑。每条回答固定显示这次请求实际使用的模型和接入模式，而不是事后读取当前设置。

自带 API：

- 预设包含 DeepSeek V4 Flash/Pro、SiliconFlow DeepSeek V3、OpenAI GPT-4o、MiniMax M2、豆包 Pro、OpenRouter GPT-4o、Groq Llama 3.3、Together Llama、MiMo 和自定义 OpenAI-compatible。
- 可编辑 Base URL、Model/Endpoint ID 和 API Key；豆包的 Model 填 `ep-…`。
- API Key 只随当前请求进入 Python stdin/HTTP header，不写 argv、SQLite、缓存、日志或研究记录。
- 自定义端点会校验 scheme、凭据、DNS/IP 和每次重定向；公网模式禁止内网、loopback 和元数据地址。

“AI 数据工具”不是第三种 AI 配置，而是 API 模式下模型可按需调用的九类只读结构化查询：

1. 组合上下文
2. 标的上下文
3. 行情
4. 公司业务
5. 估值
6. 财报
7. 新闻
8. 研报
9. 板块知识

工具不能访问任意 URL、SQL 或 Shell，也不能修改持仓、交易、笔记或板块。最多调用 6 轮，
单次结果和总上下文都有大小上限。只有用户点击“存入研究记录”才会写入 AI 回答，并在写入前脱敏。

设置页还提供当前连接状态、用当前表单快速试问、CLI/API 能力对比、来源显示和研究保存开关。
全局抽屉会展示当前页面上下文预览、页面级建议问题、工具参数/条数/来源、停止和失败重试；关闭抽屉会中止正在生成的请求。
提交后、首个文字片段返回前，抽屉会显示动态处理状态和当前阶段；收到片段后立即增量展示并保留流式光标。
如果服务端已经回复但页面仍空白，应优先检查消息是否通过 Alpine 响应式集合更新，而不是直接修改插入前的普通对象。
每日复盘页有“AI 当日复盘”，资讯雷达有“提炼当前筛选”和“一键提炼全部要点”，结果均可主动存入研究记录。

复杂个股问题默认按估值、资金、财务质量、行业景气、催化剂与风险五维分析；板块问题支持需求、供给、产业链、竞争、商业/财务、估值预期、催化与风险七维框架。简单事实题不会机械套框架。

设置页的“默认挂载范围”和“默认回答结构”会实际进入服务端上下文。浏览器只提交页面、标的、板块和布尔偏好；
持仓、笔记、行情等事实始终由服务端重新读取，不能由页面伪造。

## 板块知识

板块支持新建、编辑、软归档与恢复，并维护：

- 标签、摘要和关联标的；
- 上游/中游/下游节点、节点关系和卡脖子标记；
- 核心知识、驱动、风险、证据、待验证问题、来源 URL 和资料日期；
- 四个常驻问题：按七维框架拆解、风险信号、产业链地图、卡脖子环节。

新增表是前向兼容迁移，旧代码会忽略它们，不改变原交易、持仓、关注和笔记语义。

## 研究记录

左侧“研究记录”集中展示用户主动保存的全局问 AI、每日复盘和资讯提炼结果。记录可以展开查看来源、回到关联个股/板块、单条删除或确认后清空全部；聊天不会自动落库。

对应接口为 `GET/POST/DELETE /api/research-records` 和 `DELETE /api/research-records/:id`。

## 结构化数据 CLI

```bash
python3 scripts/dashboard_data.py --help
python3 scripts/dashboard_data.py portfolio --json
python3 scripts/dashboard_data.py portfolio --refresh --json
python3 scripts/dashboard_data.py stock-context NVDA.US --json
python3 scripts/dashboard_data.py stock-financials 0700.HK --period annual --json
python3 scripts/dashboard_data.py daily-review --market A --json
python3 scripts/dashboard_data.py intel --scope all --market all --kind all --json
python3 scripts/dashboard_data.py ai-capabilities --json
printf '{"record_id":1}' | python3 scripts/dashboard_data.py research-delete --json
```

所有子命令都接受 `--workspace` 和 `--refresh`；需要跳过新鲜 provider 缓存时才使用 `--refresh`。
它们都返回稳定的 `dashboard-v1` envelope。

## 数据库备份与恢复

在首次启用新增写入功能前备份：

```bash
mkdir -p ~/.trade-journal/results/trade-journal/db/backups
sqlite3 "$HOME/.trade-journal/results/trade-journal/db/trades.db" \
  ".backup '$HOME/.trade-journal/results/trade-journal/db/backups/trades-before-dashboard.db'"
chmod 600 "$HOME/.trade-journal/results/trade-journal/db/backups/trades-before-dashboard.db"
```

恢复前先停止 Node 服务，并保留当前库的另一份备份：

```bash
sqlite3 "$HOME/.trade-journal/results/trade-journal/db/trades.db" \
  ".restore '$HOME/.trade-journal/results/trade-journal/db/backups/trades-before-dashboard.db'"
sqlite3 "$HOME/.trade-journal/results/trade-journal/db/trades.db" "PRAGMA integrity_check;"
```

## 服务环境变量

| 变量 | 作用 |
| --- | --- |
| `HOST`, `PORT` | 监听地址和端口；默认 `127.0.0.1:8787` |
| `STJ_WORKSPACE`, `STJ_DB` | 工作区和兼容旧服务的数据库路径 |
| `STJ_DASHBOARD_V2=0` | 临时使用旧首页 |
| `STJ_API_KEY` | 可选后端 Bearer 密钥；非 loopback 启动时强制要求 |
| `STJ_PUBLIC_MODE=1` | 对自定义 AI 端点启用公网 SSRF 策略 |
| `STJ_PYTHON` | Node 调用的 Python，可用于指定虚拟环境 |
| `STJ_DATA_TIMEOUT_MS` | 结构化数据子进程超时 |
| `STJ_QUOTE_TTL_SECONDS` | 持仓/关注报价缓存秒数；默认 `180` |
| `STJ_RENDER_CHART` | 原 STJ 图表渲染脚本路径 |
| `STJ_QUOTE_TIMEOUT_MS` | 兼容旧首页的报价超时 |

## 验收

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
node --test tests/*.test.mjs
node --check scripts/live_server.mjs
node --check assets/dashboard.js
```

浏览器验收时至少检查桌面与窄屏导航、持仓盈亏红/绿与正负号、关注打开详情、
A/港/美详情、原 STJ K 线记录、财报柱图、板块完整闭环、AI 停止/错误恢复和研究记录显式保存。
