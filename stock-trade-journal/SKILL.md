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
  - "导入交易记录" "从PDF导入交易" "补交易笔记" "扫描补笔记"
  - "查询持仓" "持仓盈亏" "我的持仓"
  - "关注 XXX" "加入关注" "关注列表"
  - "分析持仓" "在线持仓" "打开持仓网页" "打开标的图表"
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
| `/stj 笔记` | 添加标的笔记 | `/stj 笔记 CORN.US holding_review 继续持有到7月中旬` |
| `/stj 关注列表` | 查看关注 | `/stj 关注列表` |
| `/stj 画像复盘` | 单标的画像复盘与纪律审计 | `/stj 画像复盘 RDDT.US` |
| `/stj 更新交易画像` | 全记录画像更新复盘 | `/stj 更新交易画像` |
| `/stj 分析持仓` | 持仓盈利、组合风险、关注列表和操作建议 | `/stj 分析一下我的持仓还有关注` |
| `/stj 证据包` | 生成持仓、关注、行情、汇率和合并暴露证据包 | `/stj 证据包 --write` |
| `/stj 行情` | 统一口径查询 A/H/美股价格、时间戳和汇率 | `/stj 行情 002803.SZ 0700.HK NVDA.US` |
| `/stj 分析 <标的>` | 直接分析单只持仓/关注标的 | `/stj 分析 RDDT.US` |
| `/stj 在线持仓` | 启动实时持仓、关注和任意标的图表网页 | `/stj 在线持仓` |
| `/stj MCP` | 启动本地 MCP server，给 Agent 调 STJ 工具 | `/stj MCP` |
| `/stj 同步` | 同步IBKR | `/stj 同步IBKR` |
| `/stj 补笔记` | 扫描导入交易并补充交易画像笔记 | `/stj 补笔记` |

---

## 核心特性

- ✅ **双表联动**: 交易记录表 + 持仓表自动同步
- ✅ **均价计算**: 买入自动计算加权均价
- ✅ **盈亏追踪**: 卖出自动计算已实现盈亏
- ✅ **多数据源**: 手动记录 / IBKR API / CSV 导入
- ✅ **导入后补笔记**: 导入交易后按交易画像逐笔补充主逻辑、周期、失效条件和加仓规则
- ✅ **统一行情口径**: `quote_adapter.py` 统一 A/H/美股价格、报价时间、来源和汇率
- ✅ **证据包快照**: `evidence_pack.py` 把持仓、关注、笔记、行情、权重和同公司暴露写入 JSON 底稿
- ✅ **Agent 工具出口**: `mcp_server.py` 把 STJ 本地数据和证据包暴露成 MCP 工具
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

### notes 表（统一标的笔记）

```sql
CREATE TABLE notes (
  id INTEGER PRIMARY KEY,
  ts_code TEXT NOT NULL,
  exchange TEXT,
  note_type TEXT NOT NULL,      -- trade_decision/watch_observation/holding_review
  note TEXT NOT NULL,
  related_trade_id INTEGER,     -- trade_decision 可关联 trades.id
  timestamp TEXT NOT NULL,
  source TEXT DEFAULT 'manual',
  created_at TEXT
);
```

`note_type` 只允许三类：

| note_type | 用途 |
|------|------|
| `trade_decision` | 交易当天的决策记录，由交易录入自动写入 |
| `watch_observation` | 未持仓或未交易时的观察记录 |
| `holding_review` | 已持仓但不交易时的复盘记录 |


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

### 1.1 统一行情和证据包

行情、汇率和报价时间统一走 `scripts/quote_adapter.py`。组合分析和自动化复盘应优先生成证据包，再基于证据包和交易画像输出动作建议。

```bash
python3 scripts/quote_adapter.py 002803.SZ 0700.HK NVDA.US --json
python3 scripts/evidence_pack.py --write --json
```

`quote_adapter.py` 返回统一字段：

| 字段 | 含义 |
|------|------|
| `price` / `currency` | 原币种价格 |
| `regular_market_time` / `bar_time` | 报价时间，优先使用 `regular_market_time` |
| `source` / `source_url` | 行情来源 |
| `cny_rate` | 仅用于人民币等值权重粗估 |
| `ok` / `error` | 行情是否确认，失败时不得用旧价格替代 |

`evidence_pack.py --write` 默认写入：

```text
~/.trade-journal/results/trade-journal/snapshots/YYYY-MM-DD-evidence-pack.json
```

证据包包含：

- 本地持仓、关注列表、最近笔记；
- 统一行情、汇率、报价时间和来源；
- 原币种浮盈亏、人民币等值粗权重；
- 同公司/同逻辑合并暴露，目前内置吉宏 `002803.SZ` + `2603.HK` 合并；
- `cash_not_included=true`，提醒现金未纳入权重。

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

### 导入交易后的笔记追问

当用户要求从 IBKR PDF、截图、CSV、Flex Query 或其他外部记录导入交易时，先完成导入、去重、持仓更新和校验；然后必须扫描本次新增交易里缺少有效交易笔记的记录。

导入元数据不算有效交易笔记。包含 `IBKR PDF import`、`source_pdf=`、`account=`、`settlement=`、`raw_code=`、`commission=`、`截图导入`、`source_images=`、`listing_exchange=` 等内容时，只能视为导入来源，不能视为交易决策。

如果发现本次新增交易缺少有效笔记，不能只说“缺少主逻辑/周期/失效条件/加仓规则”。必须立刻进入“补笔记引导模式”，按最近一笔或用户指定的那一笔输出引导卡，帮助用户补齐字段。

补笔记流程必须参考当前交易画像：

- 用户明确指定 profile 时读取指定 profile。
- 用户说“我的画像”或未指定但 `profiles/` 下只有一个 profile 时，读取该 profile。
- 多个 profile 且用户未指定时，先按通用最小字段问，不硬套某个画像，并提醒用户可指定 profile 后再补。

逐笔追问规则：

- 可以一笔一笔问，按时间顺序或用户指定顺序处理；每次只问一笔，避免一次性塞很多问题。
- 必须给“可选值 + 自由补充”的问法，帮助用户快速录入。不能只抛 4 个空字段让用户自己想。
- 追问时必须显示该交易的上下文：代码、方向、成交价、数量、日期、当前持仓、最近关注笔记或同标的上一条 `trade_decision` 摘要；如果能查到当前价，给出“当前价相对成交价”的位置，帮助用户写止跌/加仓条件。
- 必须把“失效条件”和“止跌/加仓规则”拆开问：
  - 失效条件回答“什么证明我错了，需要减仓/退出/重审”。
  - 止跌确认回答“下跌后出现什么价格结构或数据，才说明不是继续走坏”。
  - 加仓规则回答“止跌确认 + 新证据 + 仓位上限同时满足时，是否允许补；哪些情况下即使下跌也禁止补”。
- 主逻辑提示：估值便宜、增长超预期、困境反转、周期底部、情绪错杀、质量折价、事件催化、板块轮动、财报验证。
- 周期提示：短线事件 / 波段 / 中期验证 / 长期持有。若用户没说周期，不要直接替用户定性；可以给默认草案并标注“待确认”。
- 失效条件提示：收入或利润下滑、毛利率/现金流恶化、核心经营指标转弱、监管/政策恶化、竞争格局破坏、价格跌破关键位且基本面没有改善。
- 止跌确认提示：回踩买入价或观察价附近不破、站回 5/10/20 日线、放量收回关键价、财报/经营数据改善后不再创新低、事件落地后价格不跌反涨。
- 加仓规则提示：只在新财报/经营数据增强、回踩企稳、估值更便宜且失效条件未触发时加；如果只是亏损、跌破关键位、核心数据变弱或仓位超限，禁止补仓。
- 用户可以对任一笔说“跳过”“先不补”“以后再补”。跳过时不要编造 note，也不要阻塞其他导入；最终汇总列出跳过的交易。
- 若用户回答不完整，允许先写入已回答字段，但必须把缺失字段写为 `待补充` 或在最终回复中列出，不得把保守规则伪装成用户原意。
- 若用户提供一句自然语言总结，先整理成 profile 字段格式；对没有明确说出的周期、止跌位、加仓上限、复盘日期，只能给“建议草案/待确认”。除非用户已经明确表示“按你整理的写入”，否则在写入前先展示将写入的笔记草案并问用户确认或补充。

补笔记引导卡格式：

```text
要补的交易：<代码> <BUY/SELL> <数量> @ <成交价>，成交时间 <时间>
现有上下文：<最近关注笔记/上一条交易笔记/当前价相对成交价>

请补一句话也可以，我会整理成字段。重点回答：
1. 主逻辑：这次买/卖主要押什么？可选：估值回归 / 情绪错杀 / 板块轮动 / 财报验证 / 困境反转 / 长期业务拼图。
2. 周期：短线事件 / 波段 / 中期验证 / 长期持有。
3. 失效条件：什么情况说明你错了，要减仓或退出？尽量写成收入、利润、毛利率、交付、监管、价格跌破且基本面无改善等可观察条件。
4. 止跌与加仓规则：跌到哪里或出现什么信号才算止跌？只有哪些新证据出现才允许加？什么情况下即使跌了也不能补？
```

写入格式仍使用单条 `note` 字段：

```text
主逻辑: <答案>；周期: <短线/中线/长线>；核心证据: <可验证证据>；失效条件: <可观察条件>；止跌确认: <价格结构或经营数据>；加仓规则: <可加/不可加条件>；仓位上限: <可选>；目标价/观察价: <可选>；复盘日期: <可选>
```

### 扫描补充缺失交易笔记

当用户说“补笔记”“扫描补笔记”“把导入交易的笔记补一下”“检查哪些交易没有画像字段”等类似请求时，走补笔记工作流。

执行步骤：

1. 读取 `trades`、`notes` 和当前 profile。
2. 找出 `note` 为空、只有导入元数据、或缺少当前 profile 必填字段的交易。
3. 按优先级排序：未清仓持仓 > 最近新增导入 > 大额交易 > 已清仓历史交易。
4. 逐笔输出补笔记引导卡再追问；允许跳过。
5. 写回 `trades.note`，并写入或更新关联的 `notes.trade_decision`。
6. 最终输出：已补交易、跳过交易、仍缺字段、下一步建议。

### 可选：生成交易 profile

当用户说“生成交易画像”“根据我的交易记录生成 profile”“把我的策略沉淀成 profile”“新增交易 profile”等类似表达时，走 profile 生成分支。

流程文件：

```text
references/trade-profile-generation-flow.md
```

处理原则：

- 先读本地 `trades`、`positions`、`watchlist`、`notes`，总结交易行为画像。
- 判断现有 profile 是否足够；不要默认新建一堆 profile。
- 如果只是询问建议，先输出 profile 草案，不写文件。
- 只有用户明确要求“保存/创建/写入 profile”时，才写入 `profiles/<slug>.md`，并同步安装副本。
- 生成的 profile 必须保持轻量，默认必填问题不超过 5 个。
- 生成 profile 必须包含可复制好习惯、需要规避的坏习惯、交易拦截器、交易前提醒卡和画像更新记录。
- 好坏习惯判断必须标注证据等级；没有交易结果、持仓变化、复盘笔记或外部数据支持时，只能写成待验证假设。
- 画像更新前必须先做完整复盘，不能直接覆盖 profile。

### 可选：画像复盘与更新

当用户说“画像复盘 <标的>”“复盘这只股票并更新画像”“更新交易画像”“根据所有记录优化画像”等类似表达时，读取：

```text
references/profile-evolution-review-flow.md
profiles/<当前画像>.md
```

单标的复盘：

```bash
python3 scripts/profile_review.py single RDDT.US --json --write-docs
```

全记录画像更新复盘：

```bash
python3 scripts/profile_review.py all --json --write-docs
```

处理原则：

- 每次更新画像前都必须先输出完整复盘结论。
- 每次画像复盘/更新都必须默认生成两份 Markdown：
  - 单标的复盘：`<代码>-self-portrait.md` + `<代码>-profile-evidence.md`；只生成局部证据包，不更新整体画像。
  - 全记录复盘：`self-portrait-latest.md` + `executable-profile-draft-latest.md`；只有全记录复盘才形成可执行 profile 草案。
- `profile-summary-latest.md` 只是兼容旧入口，内容等同自读画像，不代表可执行 profile 草案。
- 必须先审计 `trade_decision` note：note 只是当时主张，不是事实证明；没有卖出闭环、后续 `holding_review` 或外部行情/财报/事件验证时，不能归纳为可复制好习惯。
- 单标的复盘只记录该标的暴露出的习惯、拦截器或待验证假设；不能用单一样本改写整个画像或正式 profile。
- 全记录复盘才可以更新整体画像，但必须区分 A/B/C/D 证据等级。
- 只有用户明确确认“写入/保存/更新 profile”时，才修改 `profiles/<slug>.md`。
- 更新 profile 时必须保留或更新：适用场景、禁用场景、可复制好习惯、需要规避的坏习惯、交易拦截器、交易前提醒卡、持仓复盘规则、画像更新记录。

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
| `render_chart.py` | 在线持仓页内部使用的 ECharts 图表渲染器 |
| `live_server.mjs` | 启动实时持仓、关注和任意标的图表网页 |
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
python3 scripts/watchlist.py note NVDA.US --type watch_observation --note "AI龙头，数据中心需求强劲，等回调买入"
```

不交易但要记录复盘时，使用统一笔记入口：

```bash
python3 scripts/notes.py add CORN.US --type holding_review --note "继续持有到2026-07月中旬，观察夏季玉米天气扰动"
python3 scripts/notes.py ls CORN.US
```

### 查看列表

```bash
# 查看所有关注
python3 scripts/watchlist.py ls

# 查看所有关注，并为每个标的展示最近 20 条标的笔记
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

关注列表只保存标的状态、分类、目标价、止损价和优先级；标的笔记统一写入 `notes`：

```bash
python3 scripts/watchlist.py note <代码> --type watch_observation --note <观察笔记>
python3 scripts/notes.py add <代码> --type holding_review --note <持仓复盘笔记>
```

查看关注列表时，应按标的分组展示多条标的笔记，并为每条记录显示日期和 `note_type`；不要把笔记压缩成单条“最新笔记”。

---

## 分析入口

默认分析入口是 `references/invest-research-flow.md`。组合级持仓/关注复盘还必须读取：

```text
references/portfolio-watch-analysis-flow.md
references/pre-trade-interceptor-flow.md
profiles/<用户指定或当前适用的交易画像>.md
```

### 组合级持仓与关注复盘

当用户说“分析我的持仓”“持仓盈利”“操作推荐”“分析持仓还有关注”“看看关注列表能不能买”等请求时，直接产出分析结论，不要返回提示词，也不要用图表报告代替。

组合级分析必须按 `references/portfolio-watch-analysis-flow.md` 产出“交易决策版”，不是持仓体检版。开头必须给组合状态、最大矛盾、今日/本周最重要 3 个动作，并回答“只能加一个选谁、必须减一个选谁、是否应该等待”。如果缺少外部验证，必须降低动作强度并说明需要验证的数据。

先读取本地数据：

```bash
python3 scripts/query_positions.py
python3 scripts/watchlist.py ls
```

必要时按标的补读：

```bash
python3 scripts/query_trades.py --ts-code <代码> --limit 5
python3 scripts/analyze_holdings.py context <代码或名称> --json
python3 scripts/profile_review.py single <代码> --json
```

输出必须覆盖：

- 当前持仓盈亏、原币种浮盈亏和人民币等值权重估算。
- 组合集中度、同一公司跨市场暴露、行业/宏观/币种相关性。
- 组合状态、机会成本比较和动作优先级：进攻/防守/换仓/降风险/等验证；只能加一个、必须减一个、是否等待。
- 按所选交易画像约束动作：使用 profile 中定义的仓位上限、加仓/再买规则、失效条件和复盘要求；不要硬套某个固定画像。
- 先输出画像拦截结果：触发哪些交易拦截器、允许动作、禁止动作、必须追问或补充的字段。
- 持仓处理：每个重点持仓必须给动作树，包含继续持有、加仓、减仓、退出条件、仓位比例和下一次复盘点。
- 关注列表处理：必须排序为今天可开仓、等价格、等事件/财报验证、降级/删除关注；可交易标的必须给触发价、首笔仓位、加仓规则和失效条件。
- 执行清单：优先级、标的、当前动作、触发条件、仓位动作、失效条件、下次复盘。
- 如果交易 note 没有所选 profile 要求的字段，指出需要补齐哪些字段。

禁止只写“继续持有”“持有观察”“建议关注”。这些词只能作为动作标签，后面必须跟可复盘的价格、财报、事件、仓位或时间条件。

### 单股直接分析

当用户说 `/stj 分析 <标的>`、`/stj 看看 <标的>`、`买不买/持有吗` 时，不要只输出提示词。先读取本地上下文，再联网获取最新数据，并按 `references/invest-research-flow.md` 直接产出结论。

```bash
python3 scripts/analyze_holdings.py context RDDT.US --json
python3 scripts/analyze_holdings.py context 腾讯 --json
python3 scripts/profile_review.py single RDDT.US --json
```

若用户问的是买入、加仓、减仓、卖出或继续持有，必须先读取 `references/pre-trade-interceptor-flow.md` 和当前 profile 的“交易拦截器”，输出交易前提醒卡，再给交易建议。

当前持仓回答继续持有、加仓、减仓、风险和失效条件；关注标的回答是否值得新开仓、买入触发条件、仓位计划和失效条件。

---

## 在线持仓与标的图表

用户要求“在线启动 node”“打开持仓网页”“实时持仓和关注页”“看某个代码的图”等需求时，统一启动本地 Node 服务，图表查看也在该网页内完成：

```bash
cd ~/.claude/skills/stock-trade-journal/scripts
PORT=8787 node live_server.mjs
```

浏览器访问：

```text
http://127.0.0.1:8787/
```

服务能力：

- 每次刷新实时读取 `~/.trade-journal/results/trade-journal/db/trades.db`
- 持仓表展示成本、实时价、收益率、总收益，涨红跌绿
- 关注列表和持仓共用实时行情，行情来自东方财富/Yahoo
- 点击持仓/关注标的图表时实时调用 `render_chart.py` 生成 HTML
- 页面顶部可以输入任意代码并选择周期，支持不在持仓或关注列表里的标的，例如 `META.US`、`601021.SH`、`0700.HK`
- 优先用 Node 拉 OHLC 并通过 `--price-json` 传给图表脚本，减少 Python 网络源失败的影响
- 图表会自动叠加本地交易、关注和持仓笔记；没有本地记录的代码只显示行情图

可用环境变量：`STJ_WORKSPACE`、`STJ_DB`、`STJ_RENDER_CHART`、`STJ_QUOTE_TIMEOUT_MS`、`HOST`、`PORT`。

---

## 注意事项

1. **IBKR API 限制**: 只能获取当前会话的执行记录，历史需用 Flex Query
2. **去重机制**: 使用 `ibkr_exec_id` 避免重复导入
3. **均价算法**: 买入加权平均，卖出不影响均价
4. **已实现盈亏**: 按 FIFO 简化为均价计算
