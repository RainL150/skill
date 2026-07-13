---
name: stj
description: stock-trade-journal 快捷入口。交易记录、持仓/关注、跨市场投研工作台与全局问 AI。
---

# /stj - 交易日志快捷命令

这是 `stock-trade-journal` 的快捷别名。

默认数据目录统一为 `~/.trade-journal`，数据库为
`~/.trade-journal/results/trade-journal/db/trades.db`。如需覆盖，使用
`STJ_WORKSPACE` 或各脚本的 `--workspace` 参数。

Claude 全局安装时，主 skill 脚本目录为：
`~/.claude/skills/stock-trade-journal/scripts`

## 使用方式

直接在 `/stj` 后面跟命令即可：

| 命令 | 功能 |
|------|------|
| `/stj 记录 NVDA.US 买入50股@130` | 记录交易 |
| `/stj 持仓` | 查看持仓 |
| `/stj 关注 AVGO.US` | 添加关注 |
| `/stj 关注记录 0700.HK 买入观望` | 添加观察笔记 |
| `/stj 笔记 CORN.US holding_review 继续持有到7月中旬` | 添加不交易复盘笔记 |
| `/stj 关注列表` | 查看关注列表 |
| `/stj 生成交易画像` | 根据交易记录生成/建议交易 profile |
| `/stj 画像复盘 RDDT.US` | 单标的画像复盘和纪律审计 |
| `/stj 更新交易画像` | 全记录画像更新复盘 |
| `/stj 分析持仓` | 持仓盈利、组合风险、关注列表和操作建议 |
| `/stj 证据包` | 生成持仓 + 关注 + 行情 + 合并暴露证据包 |
| `/stj 行情 NVDA.US 0700.HK` | 用统一口径查询行情、时间戳和汇率 |
| `/stj 分析 RDDT.US` | 直接分析单只持仓/关注标的 |
| `/stj 在线持仓` | 启动持仓、关注、复盘、板块与全局问 AI 投研工作台 |
| `/stj 同步IBKR` | 同步盈透数据 |
| `/stj 补笔记` | 扫描导入交易并补充交易画像笔记 |

## 处理用户请求

收到用户请求后，根据意图执行对应操作：

### 记录交易
```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 record_trade.py --ts-code <代码> --side <BUY/SELL> --price <价格> --quantity <数量> --note <交易笔记>
```

交易原因和交易备注统一写入 `--note`。默认记录交易不强制追问自定义画像问题。

### 交易录入 profile（可选）
自定义交易画像不属于主流程。只有用户明确说“用 profile”“按我的画像记录”“用 <画像名> 录入”等类似表达时，才读取主 skill 的 profile。

Profile 是可替换的外部输入，按用户指定名称选择；如果用户只说“我的画像”且 `profiles/` 下只有一个 profile，可读取该 profile。若有多个 profile 且未指定，先让用户指定，不要默认套用某个画像。

```text
~/.claude/skills/stock-trade-journal/profiles/<profile-slug>.md
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

### 生成交易 profile（可选）
当用户说“生成交易画像”“根据我的交易记录生成 profile”“把我的策略沉淀成 profile”“新增交易 profile”等类似表达时，走 profile 生成分支。

执行流程见主 skill：

```text
~/.claude/skills/stock-trade-journal/references/trade-profile-generation-flow.md
```

处理原则：

- 先读本地 `trades`、`positions`、`watchlist`、`notes`，总结交易行为画像。
- 判断现有 profile 是否足够；不要默认新建一堆 profile。
- 如果只是询问建议，先输出 profile 草案，不写文件。
- 只有用户明确要求“保存/创建/写入 profile”时，才写入 `~/.claude/skills/stock-trade-journal/profiles/<slug>.md`，并同步源 skill 的 `profiles/<slug>.md`。
- 生成的 profile 必须保持轻量，默认必填问题不超过 5 个。
- 生成或更新 profile 必须输出两份文档：给人看的 `self-portrait` 自读画像，以及给 `profiles/` 侧使用的文档。单标的复盘生成 `profile-evidence` 局部证据包；全记录复盘才生成 `executable-profile-draft` 可执行草案。
- 可复制好习惯、需要规避的坏习惯和交易拦截器必须经过 note 审计验证；`note` 只是当时主张，不是事实证明。
- 画像更新前必须执行完整复盘：单标的用 `profile_review.py single <代码> --json --write-docs`，全记录用 `profile_review.py all --json --write-docs`。

### 画像复盘与更新
当用户说“画像复盘 <标的>”“复盘这只股票更新画像”“更新交易画像”“根据所有记录优化画像”等类似表达时，走画像更新复盘流程，不要直接改 profile。

```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 profile_review.py single <代码> --json --write-docs
cd ~/.claude/skills/stock-trade-journal/scripts && python3 profile_review.py all --json --write-docs
```

然后读取主 skill：

```text
~/.claude/skills/stock-trade-journal/references/profile-evolution-review-flow.md
~/.claude/skills/stock-trade-journal/profiles/<当前画像>.md
```

必须先输出完整复盘结论、证据等级、note 审计验证、建议保留/新增/加强/降级的拦截器，并默认生成两份 Markdown。单标的复盘不更新整体画像，只生成局部证据包；全记录复盘才可以形成可执行 profile 草案。只有用户明确确认“写入/保存/更新 profile”时，才修改 profile 文件。

默认文档路径：

```text
~/.trade-journal/results/trade-journal/profile-reviews/self-portrait-latest.md
~/.trade-journal/results/trade-journal/profile-reviews/single-profile-evidence-latest.md
~/.trade-journal/results/trade-journal/profile-reviews/executable-profile-draft-latest.md
```

`profile-summary-latest.md` 只是旧兼容入口，等同自读画像。

### 查看持仓
```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 query_positions.py
```

### 统一行情口径
当用户问“查行情”“价格时间”“用最新价重算”“统一行情口径”等请求时，优先使用 `quote_adapter.py`，不要临时混用多个网页片段。

```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 quote_adapter.py 002803.SZ 0700.HK NVDA.US --json
```

输出里必须使用：

- `price` / `currency`：原币种当前价或最近收盘价；
- `regular_market_time` 或 `bar_time`：报价时间；
- `source` / `source_url`：行情来源；
- `cny_rate`：仅用于人民币等值权重粗估。

如果 `ok=false`，把该标的标为“行情未确认”，不要用旧价格硬算。

### 管理关注列表
```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 watchlist.py <add/ls/rm/up> [参数]
```

用户要求查看关注、关注列表、所有关注时，运行 `watchlist.py ls`。输出必须按标的分组展示，并列出每个标的的多条关注记录；每条关注记录都要带日期，不要只展示最新一条笔记。

### 记录关注笔记
```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 watchlist.py note <代码> --type watch_observation --note <笔记>
```

关注列表和标的笔记分开：关注列表表示标的状态，标的笔记没有买卖方向、数量和价格。

### 记录不交易笔记
不交易时不要写入 `trades.note`。统一写入 `notes`，且每条都绑定具体标的，不记录组合笔记。

`note_type` 只允许三类：

| note_type | 用途 |
|------|------|
| `trade_decision` | 交易当天的决策记录，由交易录入自动写入 |
| `watch_observation` | 未持仓或未交易时的观察记录 |
| `holding_review` | 已持仓但不交易时的复盘记录 |

```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 notes.py add <代码> --type holding_review --note <复盘笔记>
cd ~/.claude/skills/stock-trade-journal/scripts && python3 notes.py list <代码>
```

### 持仓与关注组合分析
当用户说“分析我的持仓”“持仓盈利”“分析持仓还有关注”“给我操作推荐”“看看关注列表能不能买”等组合级请求时，必须直接分析，不要输出提示词，也不要用图表报告代替。

组合级分析必须输出“交易决策版”，不是持仓体检版。开头必须给组合状态、最大矛盾、今日/本周最重要 3 个动作，并回答“只能加一个选谁、必须减一个选谁、是否应该等待”。如果缺少外部验证，必须降低动作强度并说明需要验证的数据。

执行顺序：
```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 query_positions.py
cd ~/.claude/skills/stock-trade-journal/scripts && python3 watchlist.py ls
cd ~/.claude/skills/stock-trade-journal/scripts && python3 evidence_pack.py --write --json
```

然后读取主 skill：

```text
~/.claude/skills/stock-trade-journal/references/portfolio-watch-analysis-flow.md
~/.claude/skills/stock-trade-journal/profiles/<用户指定或当前适用的交易画像>.md
```

按该流程：
- 优先使用 `evidence_pack.py --write --json` 生成证据包；证据包已包含统一行情、汇率、持仓权重和同公司合并暴露；
- 用统一行情口径重新获取价格，并说明价格时间；如果证据包里的某个 quote 失败，必须标“未确认”；
- 分原币种计算持仓浮盈亏，组合权重只做人民币等值粗估；
- 合并同一公司跨市场暴露，例如 A 股 + H 股；
- 按所选交易画像约束动作建议：使用 profile 中定义的仓位上限、加仓/再买规则、失效条件和复盘要求，不要硬套某个固定画像；
- 持仓给出动作树：继续持有/减仓/加仓/退出条件、仓位比例、触发价或事件、下次复盘点；
- 关注列表必须排序为今天可开仓、等价格、等事件/财报验证、降级/删除关注；可交易标的给出是否开仓、触发价、首笔仓位、加仓规则和失效条件；
- 输出执行清单：优先级、标的、当前动作、触发条件、仓位动作、失效条件、下次复盘；
- 若交易 note 没有所选 profile 要求的字段，指出需要补齐哪些字段。

禁止只写“继续持有”“持有观察”“建议关注”。这些词只能作为动作标签，后面必须跟可复盘的价格、财报、事件、仓位或时间条件。

### 单股直接分析
当用户说 `/stj 分析 <标的>`、`/stj 看看 <标的>`、`买不买/持有吗` 时，直接分析，不要只输出提示词。

执行顺序：
```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 analyze_holdings.py context <代码或名称> --json
cd ~/.claude/skills/stock-trade-journal/scripts && python3 profile_review.py single <代码或名称> --json
```

然后读取主 skill 的 `references/invest-research-flow.md`，按该流程：
- 先读取 `references/pre-trade-interceptor-flow.md` 和当前 profile 的交易拦截器，输出交易前提醒卡；
- 结合本地持仓/关注/交易记录；
- 加载主 skill 内置的 `references/invest-research-skills/` 原始投研框架，包括 `stock-fundamental`、`sector-research`、`shared-research-context`、`research-review`；
- 联网获取最新行情、估值、公告/财报等数据；
- 先给结论，再给依据、交易/持仓处理、失效条件和跟踪清单。

直接分析时不要依赖外部 `invest-research-skills` 是否安装；`stock-trade-journal` 已内置完整运行时 reference。

### 证据包和 MCP
当用户说“生成证据包”“保存今日快照”“为自动化保存数据底稿”等请求时，运行：

```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 evidence_pack.py --write --json
```

证据包默认写入：

```text
~/.trade-journal/results/trade-journal/snapshots/YYYY-MM-DD-evidence-pack.json
```

证据包是数据底稿，不替代交易结论。组合分析仍需读取 profile 和 `portfolio-watch-analysis-flow.md`，再输出动作树。

如果用户要求把 STJ 挂给 Claude Code / Codex / MCP 客户端，使用：

```bash
python3 ~/.claude/skills/stock-trade-journal/scripts/mcp_server.py
```

该 MCP server 暴露 `stj_query_positions`、`stj_query_notes`、`stj_quote`、`stj_evidence_pack`，只返回客观本地数据和行情证据，不直接给买卖建议。

### 在线投研工作台
当用户要求“在线启动 node”“打开持仓网页”“投研工作台”“问 AI 设置”“看某个代码的图”等类似请求时，先读取主 skill 的 `references/dashboard-guide.md`，再启动本地服务：

```bash
cd ~/.claude/skills/stock-trade-journal/scripts && PORT=8787 node live_server.mjs
```

浏览器打开：

```text
http://127.0.0.1:8787/
```

页面包含左侧菜单、持仓、关注、个股详情、原 STJ K 线记录、每日复盘、资讯雷达、板块知识、研究记录和全局问 AI。AI 完整支持订阅 CLI 与 11 个 API 预设/自定义端点；复盘与资讯可页内生成，API 模式的数据工具只读。旧 `/api/data`、`/chart`、`/charts/*` 仍兼容，`STJ_DASHBOARD_V2=0` 可恢复旧首页。

### 同步 IBKR
```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 sync_ibkr.py --port 4001 --positions --sync-positions
```

## 完整功能

完整功能文档见 `/stock-trade-journal`。
