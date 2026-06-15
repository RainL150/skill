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
  - "分析持仓" "看图" "打开图表"
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
| `/stj 分析持仓` | 持仓盈利、组合风险、关注列表和操作建议 | `/stj 分析一下我的持仓还有关注` |
| `/stj 分析 <标的>` | 直接分析单只持仓/关注标的 | `/stj 分析 RDDT.US` |
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

默认手动记录交易只写入用户提供的交易笔记，不强制追问自定义画像问题。

### 可选：交易录入 profile

自定义交易画像不属于主流程。只有用户明确说“用 profile”“按我的画像记录”“用 <画像名> 录入”等类似表达时，才读取 `profiles/` 下对应 profile。

Profile 是可替换的外部输入，按用户指定名称选择；如果用户只说“我的画像”且 `profiles/` 下只有一个 profile，可读取该 profile。若有多个 profile 且未指定，先让用户指定，不要默认套用某个画像。

```text
profiles/<profile-slug>.md
```

启用 profile 后，按所选 profile 追问缺失字段，并把回答合并进 `--note`，不要新增数据库字段，也不要改变 `record_trade.py` 的默认参数。

写入 `--note` 的推荐格式：

```text
<原始备注>；<profile 字段1>: <答案>；<profile 字段2>: <答案>；...
```

### 可选：生成交易 profile

当用户说“生成交易画像”“根据我的交易记录生成 profile”“把我的策略沉淀成 profile”“新增交易 profile”等类似表达时，走 profile 生成分支。

流程文件：

```text
references/trade-profile-generation-flow.md
```

处理原则：

- 先读本地 `trades`、`positions`、`watchlist`、`watch_notes`，总结交易行为画像。
- 判断现有 profile 是否足够；不要默认新建一堆 profile。
- 如果只是询问建议，先输出 profile 草案，不写文件。
- 只有用户明确要求“保存/创建/写入 profile”时，才写入 `profiles/<slug>.md`，并同步安装副本。
- 生成的 profile 必须保持轻量，默认必填问题不超过 5 个。

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
| `analyze_holdings.py` | 本地持仓/关注分析上下文 |
| `render_chart.py` | 生成带交易/关注标注的本地 ECharts 图表 |
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

## 分析入口

默认分析入口是 `references/invest-research-flow.md`。组合级持仓/关注复盘还必须读取：

```text
references/portfolio-watch-analysis-flow.md
profiles/<用户指定或当前适用的交易画像>.md
```

### 组合级持仓与关注复盘

当用户说“分析我的持仓”“持仓盈利”“操作推荐”“分析持仓还有关注”“看看关注列表能不能买”等请求时，直接产出分析结论，不要返回提示词，也不要用图表报告代替。

先读取本地数据：

```bash
python3 scripts/query_positions.py
python3 scripts/watchlist.py ls
```

必要时按标的补读：

```bash
python3 scripts/query_trades.py --ts-code <代码> --limit 5
python3 scripts/analyze_holdings.py context <代码或名称> --json
```

输出必须覆盖：

- 当前持仓盈亏、原币种浮盈亏和人民币等值权重估算。
- 组合集中度、同一公司跨市场暴露、行业/宏观/币种相关性。
- 按所选交易画像约束动作：使用 profile 中定义的仓位上限、加仓/再买规则、失效条件和复盘要求；不要硬套某个固定画像。
- 持仓处理：继续持有、加仓、减仓、退出条件和可观察失效条件。
- 关注列表处理：是否可开仓、触发价、首笔仓位、加仓规则和失效条件。
- 如果交易 note 没有所选 profile 要求的字段，指出需要补齐哪些字段。

### 单股直接分析

当用户说 `/stj 分析 <标的>`、`/stj 看看 <标的>`、`买不买/持有吗` 时，不要只输出提示词。先读取本地上下文，再联网获取最新数据，并按 `references/invest-research-flow.md` 直接产出结论。

```bash
python3 scripts/analyze_holdings.py context RDDT.US --json
python3 scripts/analyze_holdings.py context 腾讯 --json
```

当前持仓回答继续持有、加仓、减仓、风险和失效条件；关注标的回答是否值得新开仓、买入触发条件、仓位计划和失效条件。

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

## 注意事项

1. **IBKR API 限制**: 只能获取当前会话的执行记录，历史需用 Flex Query
2. **去重机制**: 使用 `ibkr_exec_id` 避免重复导入
3. **均价算法**: 买入加权平均，卖出不影响均价
4. **已实现盈亏**: 按 FIFO 简化为均价计算
