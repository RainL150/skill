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
  --reason "压力位先锁利润"

python3 scripts/query_trades.py \
  --ts-code 603067.SH --limit 20

python3 scripts/render_chart.py RDDT.US
```

图表默认输出到 `~/.trade-journal/results/trade-journal/charts/<代码>.html`。
脚本会为 A 股从东方财富获取 OHLC 数据，其他市场默认走 Yahoo chart API，并自动挂载本地 `trades`、`positions`、`watchlist` 记录。
如已有价格数据，可用 `--price-json path/to/ohlc.json` 跳过网络拉取。
