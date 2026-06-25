---
name: stj
description: stock-trade-journal 快捷入口。交易记录、持仓管理、关注列表、一键分析。
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
| `/stj 分析 RDDT.US` | 直接分析单只持仓/关注标的 |
| `/stj 在线持仓` | 启动实时持仓、关注和任意标的图表网页 |
| `/stj 同步IBKR` | 同步盈透数据 |

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
```

然后读取主 skill：

```text
~/.claude/skills/stock-trade-journal/references/portfolio-watch-analysis-flow.md
~/.claude/skills/stock-trade-journal/profiles/<用户指定或当前适用的交易画像>.md
```

按该流程：
- 用统一行情口径重新获取价格，并说明价格时间；
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

### 在线持仓页
当用户要求“在线启动 node”“打开持仓网页”“实时持仓和关注页”“看某个代码的图”等类似请求时，统一启动本地服务，图表查看也在该网页内完成：

```bash
cd ~/.claude/skills/stock-trade-journal/scripts && PORT=8787 node live_server.mjs
```

浏览器打开：

```text
http://127.0.0.1:8787/
```

该服务每次刷新页面实时读取 SQLite，并用东方财富/Yahoo 获取行情；点击持仓/关注标的图表或在页面输入任意代码时，会实时生成带交易/关注标注的 HTML。任意代码可以不在持仓或关注列表中，例如 `META.US`、`601021.SH`、`0700.HK`。可用环境变量：`STJ_WORKSPACE`、`STJ_DB`、`STJ_RENDER_CHART`、`STJ_QUOTE_TIMEOUT_MS`、`HOST`、`PORT`。

### 同步 IBKR
```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 sync_ibkr.py --port 4001 --positions --sync-positions
```

## 完整功能

完整功能文档见 `/stock-trade-journal`。
