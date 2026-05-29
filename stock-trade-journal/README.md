# stock-trade-journal

交易记录技能包（最小可用版）：
- 按个股写入 Markdown
- 同步写入 SQLite（trades.db）
- 保存股票交易所（手动传入或从 IBKR 合约读取）

## 目录
- `scripts/record_trade.py`：记录单笔交易（自动建表/建文件）
- `scripts/query_trades.py`：查询交易记录
- `templates/trade-entry.md`：Markdown 模板

## 示例
```bash
python3 scripts/record_trade.py \
  --workspace ~/.openclaw/workspace \
  --ts-code 603067.SH --side SELL --price 44.1 --quantity 2900 \
  --exchange SSE \
  --reason "压力位先锁利润"

python3 scripts/query_trades.py \
  --workspace ~/.openclaw/workspace \
  --ts-code 603067.SH --limit 20
```
