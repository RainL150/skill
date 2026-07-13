# stock-trade-journal

本地优先的交易日志与跨市场投研工作台：
- 按个股写入 Markdown
- 同步写入 SQLite（trades.db）
- 保存股票交易所（手动传入或从 IBKR 合约读取）
- 提供 A/港/美持仓、关注、原 STJ K 线、个股基本面、资讯、复盘、板块知识和研究记录看板
- 在所有页面接入订阅 CLI / 11 个 API 预设与自定义端点，并提供页内复盘/资讯提炼

默认工作目录为 `~/.trade-journal`，也可以通过 `STJ_WORKSPACE` 或 `--workspace` 覆盖。
默认数据库路径：`~/.trade-journal/results/trade-journal/db/trades.db`

## 目录
- `scripts/record_trade.py`：记录单笔交易（自动建表/建文件）
- `scripts/query_trades.py`：查询交易记录
- `scripts/render_chart.py`：生成带交易/关注标注的本地图表
- `scripts/live_server.mjs`：启动投研工作台与兼容旧路由
- `scripts/dashboard_data.py`：工作台结构化数据 CLI
- `templates/trade-entry.md`：Markdown 模板

## 示例
```bash
python3 scripts/record_trade.py \
  --ts-code 603067.SH --side SELL --price 44.1 --quantity 2900 \
  --exchange SSE \
  --note "压力位先锁利润"

python3 scripts/query_trades.py \
  --ts-code 603067.SH --limit 20

python3 scripts/render_chart.py RDDT.US --period 1y
python3 scripts/render_chart.py RDDT.US --period 交易以来
python3 scripts/watchlist.py ls --notes-limit 20
python3 scripts/notes.py add CORN.US --type holding_review --note "继续持有到7月中旬"
python3 scripts/profile_review.py single CORN.US --json --write-docs
python3 scripts/profile_review.py all --json --write-docs
```

## 投研工作台

```bash
python3 -m pip install -r requirements.txt
PORT=8787 node scripts/live_server.mjs
```

打开 `http://127.0.0.1:8787/`。新版页面默认启用；`STJ_DASHBOARD_V2=0` 可临时恢复旧首页，
旧 `/api/data`、`/chart` 和 `/charts/*` 路由仍兼容。AI 配置只保存在当前浏览器；
非 loopback 监听必须设置 `STJ_API_KEY`。

工作台对持仓/关注使用跨市场批量行情，对复盘/资讯使用有界并发，并通过页面快照与
stale-while-revalidate 优先展示最后成功结果。顶部刷新或 `dashboard_data.py ... --refresh`
会等待真实来源更新；报价 TTL 可用 `STJ_QUOTE_TTL_SECONDS` 调整。

完整的数据来源、AI 模型/CLI、只读数据工具、板块知识、备份恢复和验收说明见
[`references/dashboard-guide.md`](references/dashboard-guide.md)。

图表默认输出到 `~/.trade-journal/results/trade-journal/charts/<代码>.html`，并同步更新固定入口
`~/.trade-journal/results/trade-journal/charts/latest.html`。
脚本默认从东方财富获取 OHLC 数据，并自动挂载本地 `trades`、`positions`、`watchlist`、`notes` 记录。
交易原因/备注会同步写入 `notes.note_type = trade_decision`，止损/止盈会一并展示；截图导入等来源信息不会作为笔记展示。
关注列表和标的笔记分开；非交易笔记写入 `notes`，用 `watch_observation` 和 `holding_review` 区分。查看关注列表时会按标的分组展示多条笔记，并为每条记录显示日期和类型；图表也会按日期挂载这些笔记。
画像复盘使用 `profile_review.py`：单标的复盘用于交易前拦截和局部证据沉淀，不更新整体画像；全记录复盘用于更新整体画像。画像里的好习惯/坏习惯必须先经过 note 审计验证；`note` 只是当时主张，不是事实证明。加 `--write-docs` 会默认生成两份 Markdown：单标的是自读画像 + `profile-evidence` 局部证据包，全记录是自读画像 + `executable-profile-draft` 可执行草案。`profile-summary-latest.md` 只是旧兼容入口。
如已有价格数据，可用 `--price-json path/to/ohlc.json` 跳过网络拉取。
