---
name: stock-trade-journal
description: 交易日志系统，支持手动记录和 IBKR API 自动同步。交易表与持仓表联动，自动计算均价和盈亏。支持关注列表管理。
triggers:
  - /stj
  - /trade
  - /交易
  - /持仓
  - /关注
when: |
  当用户说以下内容时使用：
  - "记一下这笔交易" "记录交易" "买入/卖出 XXX"
  - "同步IBKR" "同步盈透"
  - "查询持仓" "持仓盈亏" "我的持仓"
  - "关注 XXX" "加入关注" "关注列表"
  - "分析持仓" "TradingView"
  - 或直接使用 /stj 命令
examples:
  - "/stj 记录：NVDA.US 在130买入100股"
  - "/stj 查看持仓"
  - "/stj 关注 AVGO.US --category AI芯片 --target 200"
  - "/stj 关注列表"
  - "/stj 同步IBKR"
  - "记录：603067.SH 在44.1减仓2900股"
  - "同步一下 IBKR 的交易记录"
  - "查看当前持仓"
  - "AAPL 的持仓成本是多少"
  - "关注一下 META.US，目标价 700"
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

## 快速命令

| 命令 | 功能 | 示例 |
|------|------|------|
| `/stj 记录` | 记录交易 | `/stj 记录 NVDA.US 买入100股@130` |
| `/stj 持仓` | 查看持仓 | `/stj 持仓` 或 `/stj 持仓 NVDA.US` |
| `/stj 关注` | 添加关注 | `/stj 关注 AVGO.US --target 200` |
| `/stj 关注列表` | 查看关注 | `/stj 关注列表` |
| `/stj 分析` | TradingView分析 | `/stj 分析` |
| `/stj 同步` | 同步IBKR | `/stj 同步IBKR` |
| `/stj web` | 启动Web界面 | `/stj web` |

---

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
  exchange TEXT,                -- 交易所
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
  exchange TEXT,                -- 交易所
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
  --ts-code AAPL.US \
  --exchange NASDAQ \
  --side BUY \
  --price 150.5 \
  --quantity 100 \
  --reason "看好AI业务"
```

输出：
```
✅ 交易已记录: AAPL.US BUY 100 @ 150.5
   交易所: NASDAQ
   金额: 15050.00 CNY
   持仓变化: 0 -> 100
   当前均价: 150.5000
```

### 2. 查询持仓

```bash
# 查看所有持仓
python3 scripts/query_positions.py

# 查询特定股票
python3 scripts/query_positions.py --ts-code AAPL.US

# 包含已清仓股票
python3 scripts/query_positions.py --all

# JSON 格式输出
python3 scripts/query_positions.py --json
```

### 3. 查询交易记录

```bash
python3 scripts/query_trades.py

# 查询特定股票
python3 scripts/query_trades.py --ts-code AAPL.US

# 最近 N 条
python3 scripts/query_trades.py --limit 20
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
python3 scripts/sync_ibkr.py --port 4001

# 同步 IBKR 持仓到本地
python3 scripts/sync_ibkr.py --port 4001 --sync-positions

# 只查看 IBKR 持仓（不写入）
python3 scripts/sync_ibkr.py --port 4001 --positions --readonly

# 查看本地数据库持仓
python3 scripts/sync_ibkr.py --local
```

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--workspace` | 工作目录 | `STJ_WORKSPACE` 或 `~/.trade-journal` |
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
| `watchlist.py` | 关注列表管理 |
| `analyze_positions.py` | TradingView 分析 |
| `sync_ibkr.py` | IBKR API 同步 |
| `web/app.py` | Web 可视化界面 |

---

## 关注列表

管理股票关注列表，支持分类、目标价、止损价、优先级等。

### 添加关注

```bash
# 基础添加
python3 scripts/watchlist.py add NVDA.US

# 完整参数
python3 scripts/watchlist.py add NVDA.US \
  --name "NVIDIA" \
  --category "AI芯片" \
  --target 150 \
  --stop 120 \
  --reason "AI龙头，数据中心需求强劲" \
  --priority 2 \
  --note "等回调买入"
```

### 查看列表

```bash
# 查看所有关注
python3 scripts/watchlist.py ls

# 按分类筛选
python3 scripts/watchlist.py ls -c "AI芯片"

# JSON 格式
python3 scripts/watchlist.py ls --json

# 查看单个股票
python3 scripts/watchlist.py show NVDA.US
```

### 更新关注

```bash
# 更新目标价
python3 scripts/watchlist.py up NVDA.US --target 160

# 更新状态为已买入
python3 scripts/watchlist.py up NVDA.US --status bought

# 更新优先级
python3 scripts/watchlist.py up NVDA.US --priority 1
```

### 删除关注

```bash
python3 scripts/watchlist.py rm NVDA.US
```

### 查看分类

```bash
python3 scripts/watchlist.py cats
```

### 参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `--name` | 股票名称 | "NVIDIA" |
| `--category`, `-c` | 分类标签 | "AI芯片" |
| `--target`, `-t` | 目标价 | 150.0 |
| `--stop`, `-s` | 止损价 | 120.0 |
| `--reason`, `-r` | 关注原因 | "技术突破" |
| `--priority`, `-p` | 优先级 (0=普通, 1=重点⭐, 2=紧急🔥) | 2 |
| `--status` | 状态 (watching/bought/removed) | watching |
| `--note`, `-n` | 备注 | "等回调" |

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
python3 web/app.py
# 指定端口
python3 web/app.py --port 8080

# 允许局域网访问
python3 web/app.py --host 0.0.0.0
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
| `--workspace` | 工作目录 | `STJ_WORKSPACE` 或 `~/.trade-journal` |
| `--port` | 端口号 | 5000 |
| `--host` | 监听地址 | 127.0.0.1 |
| `--debug` | 调试模式 | - |

---

## TradingView 持仓分析

提供 TradingView 图表链接生成和持仓分析功能。

### 命令

```bash
# 显示所有持仓的 TradingView 链接
python3 scripts/analyze_positions.py link

# 显示特定股票链接
python3 scripts/analyze_positions.py link --ts-code AAPL.US

# 批量打开 TradingView 图表（默认 5 个）
python3 scripts/analyze_positions.py tradingview

# 打开所有持仓图表
python3 scripts/analyze_positions.py tv --all

# 指定时间周期 (1,5,15,30,60,240,D,W,M)
python3 scripts/analyze_positions.py tv --interval W

# 生成持仓分析报告
python3 scripts/analyze_positions.py report

# 导出报告到文件
python3 scripts/analyze_positions.py report -o report.md
```

### 代码转换规则

| 本地格式 | TradingView 格式 |
|----------|------------------|
| AAPL.US | NASDAQ:AAPL |
| 0700.HK | HKEX:0700 |
| 600519.SH | SSE:600519 |
| 000001.SZ | SZSE:000001 |

### 分析报告内容

- 📊 持仓概览（数量、总成本、已实现盈亏）
- 🌍 按市场分布统计
- 📈 持仓详情表格（含 TradingView 链接）
- 🔗 快捷链接汇总

---

## 与 tradingview-quantitative 集成

如果已安装 `tradingview-quantitative` skill，可配合使用获取更强大的分析能力：

### 持仓技术分析

```
# 1. 查询持仓
python3 scripts/query_positions.py --json

# 2. 使用 tradingview-quantitative 分析（在 Claude 中）
请分析我的持仓股票：AAPL.US, NVDA.US, 0700.HK 的技术面
```

### 可用的 TradingView 工具

| 工具 | 用途 | 示例 |
|------|------|------|
| `get_quote` | 实时报价 | 获取 AAPL 最新价格 |
| `get_price` | K线数据 | 获取日/周线图 |
| `get_ta` | 技术分析 | RSI、MACD 等指标 |
| `get_news` | 新闻资讯 | 相关新闻动态 |
| `search_market` | 搜索标的 | 查找股票代码 |

### 推荐工作流

1. **日常检视**: 查持仓 → TradingView 技术分析 → 识别风险
2. **交易决策**: 记录交易 → 更新持仓 → 图表确认
3. **周末复盘**: 生成报告 → 批量分析 → 调整策略

---

## 注意事项

1. **IBKR API 限制**: 只能获取当前会话的执行记录，历史需用 Flex Query
2. **去重机制**: 使用 `ibkr_exec_id` 避免重复导入
3. **均价算法**: 买入加权平均，卖出不影响均价
4. **已实现盈亏**: 按 FIFO 简化为均价计算
