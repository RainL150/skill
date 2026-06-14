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
  - "分析持仓" "TradingView" "看图" "打开图表"
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
| `/stj 关注记录` | 添加观察笔记 | `/stj 关注记录 0700.HK 买入观望` |
| `/stj 关注列表` | 查看关注 | `/stj 关注列表` |
| `/stj ah 分析` | 直接分析持仓/关注标的 | `/stj ah RDDT分析` |
| `/stj ah` | analyze_holdings 提示词/任务清单 | `/stj ah prompt RDDT.US` |
| `/stj ah 腾讯` | 关注标的买入候选分析提示词 | `/stj ah prompt 腾讯` |
| `/stj analyze_hoding` | analyze_holdings 拼写容错别名 | `/stj analyze_hoding prompt` |
| `/stj tv` | TradingView 链接/报告/打开图表 | `/stj tv link RDDT.US` |
| `/stj 看图` | 生成带交易/关注标注的本地图表 | `/stj 看图 RDDT.US` |
| `/stj 同步` | 同步IBKR | `/stj 同步IBKR` |

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
  stop_loss REAL,               -- 止损价
  take_profit TEXT,             -- 止盈目标
  note TEXT,                    -- 交易笔记/交易原因
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
  --note "看好AI业务"
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
| `render_chart.py` | 生成带交易/关注标注的本地 ECharts 图表 |
| `analyze_positions.py` | TradingView 分析 |
| `sync_ibkr.py` | IBKR API 同步 |

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
  --priority 2

# 添加观察笔记
python3 scripts/watchlist.py note NVDA.US --note "AI龙头，数据中心需求强劲，等回调买入"
```

### 查看列表

```bash
# 查看所有关注
python3 scripts/watchlist.py ls

# 查看所有关注，并为每个标的展示最近 20 条关注记录
python3 scripts/watchlist.py ls --notes-limit 20

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
| `--priority`, `-p` | 优先级 (0=普通, 1=重点⭐, 2=紧急🔥) | 2 |
| `--status` | 状态 (watching/bought/removed) | watching |

关注列表只保存标的状态、分类、目标价、止损价和优先级；关注笔记统一写入关注记录时间线：

```bash
python3 scripts/watchlist.py note <代码> --note <观察笔记>
```

查看关注列表时，应按标的分组展示多条关注记录，并为每条记录显示日期；不要把关注笔记压缩成单条“最新笔记”。

---

## TradingView 持仓分析

提供 TradingView 图表链接生成和持仓分析功能。

### 与 analyze_holdings 的区别

| 入口 | 脚本 | 用途 | 示例 |
|------|------|------|------|
| `/stj ah ...` | `analyze_holdings.py` + `references/invest-research-flow.md` | 直接分析或生成提示词；持仓用于持有分析，关注标的用于买入候选分析 | `/stj ah RDDT分析` |
| `/stj tv ...` | `analyze_positions.py` | 生成 TradingView 链接、打开图表、生成持仓报告 | `/stj tv link 0700.HK` |

优先按显式前缀区分：用户说 `ah`、`analyze_holdings`、`analyze_hoding`、`分析提示词` 时走 `analyze_holdings.py`；用户说 `tv`、`TradingView`、`图表链接`、`持仓报告` 时走 `analyze_positions.py`。

### 内置投研框架

`stock-trade-journal` 已内置 `invest-research-skills` 的运行时材料，不依赖外部 skill 是否安装：

```text
references/invest-research-skills/
├── SKILL.md
├── stock-fundamental/
│   ├── SKILL.md
│   ├── assets/report-template.md
│   └── references/
├── sector-research/
│   ├── SKILL.md
│   ├── assets/
│   ├── references/
│   └── scripts/calc.py
├── shared-research-context/
│   ├── SKILL.md
│   └── references/
└── research-review/
    ├── SKILL.md
    ├── assets/
    └── references/
```

直接分析时先读 `references/invest-research-flow.md`，再按任务需要加载上面的内部 reference。不要把这一步简化成“生成 prompt”。

### ah 直接分析工作流

当用户说 `/stj ah <标的>分析`、`/stj ah prompt <标的>分析`、`/stj ah analyze <标的>`、`/stj 分析 <标的>`、`/stj 看看 <标的>`、`买不买/持有吗` 时，不要只输出 prompt。先读取本地上下文，再联网获取最新数据，并按 `references/invest-research-flow.md` 直接产出结论。

本地上下文命令：

```bash
python3 scripts/analyze_holdings.py context RDDT.US --json
python3 scripts/analyze_holdings.py context rddt分析 --json
python3 scripts/analyze_holdings.py context 腾讯 --json
```

输出要求：

- 当前持仓：回答继续持有、加仓、减仓、风险和失效条件。
- 关注标的：回答是否值得新开仓买入、买入触发条件、仓位计划和失效条件。
- 必须结合最新行情、估值、财报/公告；优先官方 IR/SEC/交易所公告。
- 先结论后依据，不要把 `invest-research-skills` 框架当成机械章节。

### analyze_holdings 提示词/任务触发方式

```bash
# 组合分析提示词
python3 scripts/analyze_holdings.py prompt

# 单股分析提示词；支持代码或关注列表名称
python3 scripts/analyze_holdings.py prompt 0700.HK
python3 scripts/analyze_holdings.py prompt 腾讯

# 快速分析提示词
python3 scripts/analyze_holdings.py quick 0700.HK
python3 scripts/analyze_holdings.py quick 腾讯

# 本地分析上下文
python3 scripts/analyze_holdings.py context 0700.HK --json

# 分析任务清单
python3 scripts/analyze_holdings.py tasks
```

对应自然语言：

- `/stj ah prompt`
- `/stj ah prompt 0700.HK`
- `/stj ah prompt 腾讯`
- `/stj ah RDDT分析`
- `/stj ah prompt RDDT分析`
- `/stj ah analyze RDDT.US`
- `/stj ah quick 0700.HK`
- `/stj ah quick 腾讯`
- `/stj ah tasks`
- `/stj analyze_hoding prompt`
- `/stj 分析持仓`
- `/stj 快速分析 0700.HK`

只有用户显式使用 `prompt` 且没有“分析/看看/买不买/持有吗”等分析意图时，才返回脚本输出本身；用户说“分析”时直接执行上面的投研分析工作流。

### TradingView 触发方式

对应自然语言：

- `/stj tv link`
- `/stj tv link 0700.HK`
- `/stj tv report`
- `/stj tv open 0700.HK`
- `/stj tv open all`

对应脚本命令：

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

## 本地标注图表

当用户说“看图”“打开图表”“给我 RDDT 的图”等需求时，优先生成本地 HTML 图表：

```bash
python3 scripts/render_chart.py RDDT.US

# 指定区间和默认图表类型
python3 scripts/render_chart.py RDDT.US --period 1y --chart-type candlestick

# 支持近一周、一个月、半年、一年、三年、交易以来
python3 scripts/render_chart.py RDDT.US --period 1w
python3 scripts/render_chart.py RDDT.US --period 交易以来

# 使用本地 OHLC JSON，跳过网络拉取
python3 scripts/render_chart.py RDDT.US --price-json prices.json
```

输出路径默认是：

```
~/.trade-journal/results/trade-journal/charts/<代码>.html
```

每次生成也会同步更新固定入口：

```
~/.trade-journal/results/trade-journal/charts/latest.html
```

这个文件会自动装载最近一次生成结果，适合固定收藏或让 `/stj 看图` 每次打开同一个入口。

图表模板来自 `templates/stock-chart.html`，抽取自 `baijuyi_fe` 的 ECharts stock chart 组件。生成时会自动读取本地数据库：

- 行情：默认从东方财富获取 OHLC 数据，`--price-json` 可跳过网络使用本地数据
- `trades`：BUY/SELL 交易会贴近最近一根 K 线，显示为 B/S 标记
- `trades` 笔记：交易原因/备注统一写入 `note`，止损/止盈触发条件会一并展示；“截图导入”等来源信息不作为笔记
- `positions`：持仓均价会显示为水平线
- `positions` + 最新收盘价：自动计算市值、总体浮盈和收益率
- `watchlist`：关注列表只管理标的状态、分类、目标价、止损价等
- `watch_notes`：关注记录是无买卖行为的观察笔记，会按日期挂到图上并支持 hover

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
