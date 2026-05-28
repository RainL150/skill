---
name: stock-trade-journal
description: 交易日志系统，支持手动记录和 IBKR API 自动同步。交易表与持仓表联动，自动计算均价和盈亏。
when: 当用户说"记一下这笔交易""记录交易""同步IBKR""查询持仓""持仓盈亏"时使用。
examples:
  - "记录：603067.SH 在44.1减仓2900股"
  - "同步一下 IBKR 的交易记录"
  - "查看当前持仓"
  - "AAPL 的持仓成本是多少"
metadata:
  {
    "openclaw": {
      "emoji": "📒",
      "requires": { "bins": ["python3"] }
    }
  }
---

# stock-trade-journal

交易日志系统，支持手动记录和 IBKR API 自动同步。**交易表与持仓表联动**，每次交易自动更新持仓、均价和已实现盈亏。

## 核心特性

- ✅ **双表联动**: 交易记录表 + 持仓表自动同步
- ✅ **均价计算**: 买入自动计算加权均价
- ✅ **盈亏追踪**: 卖出自动计算已实现盈亏
- ✅ **多数据源**: 手动记录 / IBKR API / CSV 导入
- ✅ **双写存储**: SQLite + Markdown

---

## 数据库结构

### trades 表（交易记录）

```sql
CREATE TABLE trades (
  id INTEGER PRIMARY KEY,
  ts_code TEXT NOT NULL,        -- 股票代码
  side TEXT NOT NULL,           -- BUY/SELL
  price REAL NOT NULL,          -- 成交价
  quantity INTEGER NOT NULL,    -- 数量
  amount REAL,                  -- 金额
  position_before INTEGER,      -- 交易前持仓
  position_after INTEGER,       -- 交易后持仓
  reason TEXT,                  -- 交易原因
  stop_loss REAL,               -- 止损价
  take_profit TEXT,             -- 止盈目标
  note TEXT,
  timestamp TEXT NOT NULL,
  source TEXT DEFAULT 'manual', -- manual/ibkr/import
  ibkr_exec_id TEXT,
  commission REAL,
  currency TEXT
);
```

### positions 表（持仓）

```sql
CREATE TABLE positions (
  id INTEGER PRIMARY KEY,
  ts_code TEXT NOT NULL UNIQUE, -- 股票代码（唯一）
  quantity INTEGER NOT NULL,    -- 当前持仓
  avg_cost REAL,                -- 平均成本
  total_cost REAL,              -- 总成本
  market_price REAL,            -- 最新市价
  market_value REAL,            -- 市值
  unrealized_pnl REAL,          -- 未实现盈亏
  realized_pnl REAL DEFAULT 0,  -- 已实现盈亏
  currency TEXT,
  first_buy_date TEXT,          -- 首次买入
  last_trade_date TEXT,         -- 最后交易
  updated_at TEXT
);
```

### 联动逻辑

| 操作 | 持仓变化 | 均价变化 | 已实现盈亏 |
|------|----------|----------|------------|
| **买入** | +数量 | 加权重算 | 不变 |
| **卖出** | -数量 | 不变 | +=(卖价-均价)*数量 |
| **清仓** | →0 | →0 | 累加最后一笔 |

---

## 使用方法

### 1. 手动记录交易

```bash
python3 scripts/record_trade.py \
  --workspace ~/.openclaw/workspace \
  --ts-code AAPL.US \
  --side BUY \
  --price 150.5 \
  --quantity 100 \
  --reason "看好AI业务"
```

输出：
```
✅ 交易已记录: AAPL.US BUY 100 @ 150.5
   金额: 15050.00 CNY
   持仓变化: 0 -> 100
   当前均价: 150.5000
```

### 2. 查询持仓

```bash
# 查看所有持仓
python3 scripts/query_positions.py --workspace ~/.openclaw/workspace

# 查询特定股票
python3 scripts/query_positions.py --workspace ~/.openclaw/workspace --ts-code AAPL.US

# 包含已清仓股票
python3 scripts/query_positions.py --workspace ~/.openclaw/workspace --all

# JSON 格式输出
python3 scripts/query_positions.py --workspace ~/.openclaw/workspace --json
```

### 3. 查询交易记录

```bash
python3 scripts/query_trades.py --workspace ~/.openclaw/workspace

# 查询特定股票
python3 scripts/query_trades.py --workspace ~/.openclaw/workspace --ts-code AAPL.US

# 最近 N 条
python3 scripts/query_trades.py --workspace ~/.openclaw/workspace --limit 20
```

---

## IBKR API 同步

### 前置条件

1. **安装依赖**
   ```bash
   pip install ib_insync
   ```

2. **启动 TWS 或 IB Gateway**
   - 启用 API: Edit > Global Configuration > API > Settings
   - 勾选 "Enable ActiveX and Socket Clients"

3. **端口**
   | 模式 | 端口 |
   |------|------|
   | TWS Paper | 7497 |
   | TWS Live | 7496 |
   | Gateway Paper | 4002 |
   | Gateway Live | 4001 |

### 同步命令

```bash
# 同步交易记录 + 更新持仓
python3 scripts/sync_ibkr.py \
  --workspace ~/.openclaw/workspace \
  --port 4001

# 同步 IBKR 持仓到本地
python3 scripts/sync_ibkr.py \
  --workspace ~/.openclaw/workspace \
  --port 4001 \
  --sync-positions

# 只查看 IBKR 持仓（不写入）
python3 scripts/sync_ibkr.py \
  --workspace ~/.openclaw/workspace \
  --port 4001 \
  --positions --readonly

# 查看本地数据库持仓
python3 scripts/sync_ibkr.py \
  --workspace ~/.openclaw/workspace \
  --local
```

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--workspace` | 工作目录 | (必填) |
| `--port` | TWS/Gateway 端口 | 7497 |
| `--days` | 同步最近 N 天 | 7 |
| `--positions` | 显示 IBKR 持仓 | - |
| `--sync-positions` | 同步持仓到本地 | - |
| `--readonly` | 只读模式 | - |
| `--local` | 显示本地数据库 | - |

---

## 文件结构

```
{workspace}/results/trade-journal/
├── db/
│   └── trades.db          # SQLite 数据库
└── records/
    ├── AAPL.US.md         # 按股票的交易记录
    ├── 0700.HK.md
    └── 603067.SH.md
```

---

## 代码转换规则

| 交易所 | 示例 |
|--------|------|
| 美股 (NASDAQ/NYSE) | AAPL → AAPL.US |
| 港股 (SEHK) | 700 → 0700.HK |
| A股 (沪) | 600519 → 600519.SH |
| A股 (深) | 000001 → 000001.SZ |

---

## 脚本清单

| 脚本 | 功能 |
|------|------|
| `db_schema.py` | 数据库结构和联动逻辑 |
| `record_trade.py` | 手动记录交易 |
| `query_trades.py` | 查询交易记录 |
| `query_positions.py` | 查询持仓 |
| `sync_ibkr.py` | IBKR API 同步 |
| `web/app.py` | Web 可视化界面 |

---

## Web 可视化界面

提供浏览器访问的可视化 Dashboard，实时查看持仓和交易记录。

### 安装依赖

```bash
pip install flask
```

### 启动服务

```bash
# 启动 Web 服务 (默认端口 5000)
python3 web/app.py --workspace ~/.openclaw/workspace

# 指定端口
python3 web/app.py --workspace ~/.openclaw/workspace --port 8080

# 允许局域网访问
python3 web/app.py --workspace ~/.openclaw/workspace --host 0.0.0.0
```

### 访问地址

启动后访问: **http://localhost:5000**

### 功能特性

| 功能 | 说明 |
|------|------|
| 📊 **持仓表** | 代码、数量、均价、成本、盈亏 |
| 📝 **交易记录** | 时间、方向、价格、数量、来源 |
| 📈 **统计卡片** | 持仓数、总成本、已实现盈亏、交易笔数 |
| 🔄 **自动刷新** | 每 30 秒自动更新数据 |
| 📱 **响应式** | 支持手机/平板访问 |
| 🌙 **暗色主题** | 护眼设计 |

### API 端点

| 端点 | 说明 |
|------|------|
| `GET /` | Web 界面首页 |
| `GET /api/stats` | 统计数据 |
| `GET /api/positions` | 持仓列表 |
| `GET /api/trades?limit=50` | 交易记录 |
| `GET /api/position/<ts_code>` | 单个持仓详情 |

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--workspace` | 工作目录 | (必填) |
| `--port` | 端口号 | 5000 |
| `--host` | 监听地址 | 127.0.0.1 |
| `--debug` | 调试模式 | - |

---

## 注意事项

1. **IBKR API 限制**: 只能获取当前会话的执行记录，历史需用 Flex Query
2. **去重机制**: 使用 `ibkr_exec_id` 避免重复导入
3. **均价算法**: 买入加权平均，卖出不影响均价
4. **已实现盈亏**: 按 FIFO 简化为均价计算
