---
name: stock-trade-journal
description: 按统一规则记录交易流水。支持手动记录和 IBKR API 自动同步。按个股落 Markdown，同时写入 SQLite 便于统计与量化复盘。
when: 当用户说"记一下这笔交易""记录交易""建交易日志""同步IBKR交易""查询持仓"时使用。
examples:
  - "记录：603067.SH 在44.1减仓2900股，剩余34000"
  - "把这笔交易按模板记下来"
  - "查一下振华股份最近交易流水"
  - "同步一下 IBKR 的交易记录"
  - "显示 IBKR 当前持仓"
metadata:
  {
    "openclaw": {
      "emoji": "📒",
      "requires": { "bins": ["python3"] }
    }
  }
---

# stock-trade-journal

## 固定存储位置
- `results/trade-journal/records/<TS_CODE>.md`
- `results/trade-journal/db/trades.db`

## 执行规则
1. 每次交易动作都记录（买/卖/加/减）。
2. 同时写 Markdown + SQLite（双写）。
3. Markdown 按个股持续追加，数据库用于后续统计计算。

---

## 方式一：手动记录交易

```bash
python3 scripts/record_trade.py \
  --workspace ~/.openclaw/workspace \
  --ts-code 603067.SH --side SELL --price 44.1 --quantity 2900 \
  --position-before 36900 --position-after 34000 \
  --reason "压力位先锁利润" --stop-loss 37.2 --take-profit "45.5分批"
```

---

## 方式二：IBKR API 自动同步 (新增)

从 Interactive Brokers (盈透证券) 自动同步交易记录。

### 前置条件

1. **安装依赖**
   ```bash
   pip install ib_insync
   ```

2. **运行 TWS 或 IB Gateway**
   - 下载: https://www.interactivebrokers.com/en/trading/tws.php
   - 启用 API: Edit > Global Configuration > API > Settings
   - 勾选 "Enable ActiveX and Socket Clients"

3. **端口说明**
   | 模式 | 端口 |
   |------|------|
   | TWS Paper Trading | 7497 |
   | TWS Live Trading | 7496 |
   | IB Gateway Paper | 4002 |
   | IB Gateway Live | 4001 |

### 同步交易记录

```bash
# 同步最近 7 天的交易 (Paper Trading)
python3 scripts/sync_ibkr.py \
  --workspace ~/.openclaw/workspace \
  --port 7497

# 同步 Live Trading
python3 scripts/sync_ibkr.py \
  --workspace ~/.openclaw/workspace \
  --port 7496

# 同步最近 30 天
python3 scripts/sync_ibkr.py \
  --workspace ~/.openclaw/workspace \
  --days 30
```

### 查看持仓

```bash
python3 scripts/sync_ibkr.py \
  --workspace ~/.openclaw/workspace \
  --positions --readonly
```

### 完整参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--workspace` | 工作目录 | (必填) |
| `--host` | TWS/Gateway 主机 | 127.0.0.1 |
| `--port` | TWS/Gateway 端口 | 7497 |
| `--client-id` | 客户端 ID | 1 |
| `--days` | 同步最近 N 天 | 7 |
| `--positions` | 显示当前持仓 | - |
| `--readonly` | 只读模式，不写入 | - |

### 代码转换规则

| IBKR 交易所 | 转换结果 |
|-------------|----------|
| SMART/NASDAQ/NYSE | AAPL → AAPL.US |
| SEHK | 700 → 0700.HK |
| SEHKNTL/SEHKSZSE | 600519 → 600519.SH |

---

## 查询交易记录

```bash
python3 scripts/query_trades.py --workspace ~/.openclaw/workspace

# 查询特定股票
python3 scripts/query_trades.py --workspace ~/.openclaw/workspace --ts-code 603067.SH

# 查询最近 N 条
python3 scripts/query_trades.py --workspace ~/.openclaw/workspace --limit 20
```

---

## 数据库结构

```sql
CREATE TABLE trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_code TEXT NOT NULL,        -- 股票代码 (如 603067.SH, AAPL.US)
  side TEXT NOT NULL,           -- BUY/SELL
  price REAL NOT NULL,          -- 成交价格
  quantity INTEGER NOT NULL,    -- 成交数量
  position_before INTEGER,      -- 交易前持仓
  position_after INTEGER,       -- 交易后持仓
  reason TEXT,                  -- 交易原因
  stop_loss REAL,               -- 止损价
  take_profit TEXT,             -- 止盈目标
  note TEXT,                    -- 备注
  timestamp TEXT NOT NULL,      -- 时间戳
  source TEXT DEFAULT 'manual', -- 来源: manual/ibkr
  ibkr_exec_id TEXT,            -- IBKR 执行 ID
  ibkr_order_id INTEGER,        -- IBKR 订单 ID
  commission REAL,              -- 佣金
  currency TEXT                 -- 货币
);
```

---

## 注意事项

1. **IBKR API 限制**: 只能获取最近 7 天的执行记录，历史记录需通过 Flex Query 导出
2. **去重机制**: 使用 `ibkr_exec_id` 避免重复导入
3. **只读模式**: 脚本只读取数据，不会下单或修改 IBKR 账户
