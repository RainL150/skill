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
| `/stj 关注列表` | 查看关注列表 |
| `/stj 生成交易画像` | 根据交易记录生成/建议交易 profile |
| `/stj 分析持仓` | 持仓盈利、组合风险、关注列表和操作建议 |
| `/stj 分析 RDDT.US` | 直接分析单只持仓/关注标的 |
| `/stj 看图 RDDT.US` | 生成带交易/关注标注的本地图表 |
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

- 先读本地 `trades`、`positions`、`watchlist`、`watch_notes`，总结交易行为画像。
- 判断现有 profile 是否足够；不要默认新建一堆 profile。
- 如果只是询问建议，先输出 profile 草案，不写文件。
- 只有用户明确要求“保存/创建/写入 profile”时，才写入 `~/.claude/skills/stock-trade-journal/profiles/<slug>.md`，并同步源 skill 的 `profiles/<slug>.md`。
- 生成的 profile 必须保持轻量，默认必填问题不超过 5 个。

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
cd ~/.claude/skills/stock-trade-journal/scripts && python3 watchlist.py note <代码> --note <笔记>
```

关注列表和关注记录分开：关注列表表示标的状态，关注记录是类似交易记录的观察笔记，没有买卖方向、数量和价格。

### 持仓与关注组合分析
当用户说“分析我的持仓”“持仓盈利”“分析持仓还有关注”“给我操作推荐”“看看关注列表能不能买”等组合级请求时，必须直接分析，不要输出提示词，也不要用图表报告代替。

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
- 持仓给出继续持有/减仓/加仓/退出条件；关注标的给出是否开仓、触发价、仓位计划和失效条件；
- 若交易 note 没有所选 profile 要求的字段，指出需要补齐哪些字段。

### 单股直接分析
当用户说 `/stj 分析 <标的>`、`/stj 看看 <标的>`、`买不买/持有吗` 时，直接分析，不要只输出提示词。

执行顺序：
```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 analyze_holdings.py context <代码或名称> --json
```

然后读取主 skill 的 `references/invest-research-flow.md`，按该流程：
- 结合本地持仓/关注/交易记录；
- 加载主 skill 内置的 `references/invest-research-skills/` 原始投研框架，包括 `stock-fundamental`、`sector-research`、`shared-research-context`、`research-review`；
- 联网获取最新行情、估值、公告/财报等数据；
- 先给结论，再给依据、交易/持仓处理、失效条件和跟踪清单。

直接分析时不要依赖外部 `invest-research-skills` 是否安装；`stock-trade-journal` 已内置完整运行时 reference。

### 看图
```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 render_chart.py <代码> --period 1y
```

可用时间范围：`1w`、`1mo`、`6mo`、`1y`、`3y`、`trade`，也支持中文 `近一周`、`一个月`、`半年`、`一年`、`三年`、`交易以来`。

生成的 HTML 默认保存到 `~/.trade-journal/results/trade-journal/charts/<代码>.html`，并同步更新固定入口
`~/.trade-journal/results/trade-journal/charts/latest.html`。

### 同步 IBKR
```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 sync_ibkr.py --port 4001 --positions --sync-positions
```

## 完整功能

完整功能文档见 `/stock-trade-journal`。
