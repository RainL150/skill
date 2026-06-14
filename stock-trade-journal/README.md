# stock-trade-journal

交易记录技能包（最小可用版）：
- 按个股写入 Markdown
- 同步写入 SQLite（trades.db）
- 保存股票交易所（手动传入或从 IBKR 合约读取）

默认工作目录为 `~/.trade-journal`，也可以通过 `STJ_WORKSPACE` 或 `--workspace` 覆盖。
默认数据库路径：`~/.trade-journal/results/trade-journal/db/trades.db`

## 目录
- `scripts/record_trade.py`：记录单笔交易（自动建表/建文件）
- `scripts/query_trades.py`：查询交易记录
- `scripts/render_chart.py`：生成带交易/关注标注的本地图表
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
```

图表默认输出到 `~/.trade-journal/results/trade-journal/charts/<代码>.html`，并同步更新固定入口
`~/.trade-journal/results/trade-journal/charts/latest.html`。
脚本默认从东方财富获取 OHLC 数据，并自动挂载本地 `trades`、`positions`、`watchlist`、`watch_notes` 记录。
交易原因/备注统一写入交易笔记 `note`，止损/止盈会一并展示；截图导入等来源信息不会作为笔记展示。
关注列表和关注记录分开；关注记录写入 `watch_notes`，是无买卖行为的观察笔记。查看关注列表时会按标的分组展示多条关注记录，并为每条记录显示日期；图表也会按日期挂载这些笔记。
如已有价格数据，可用 `--price-json path/to/ohlc.json` 跳过网络拉取。
