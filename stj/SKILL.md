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
| `/stj ah RDDT分析` | 直接分析持仓/关注标的 |
| `/stj ah analyze RDDT.US` | 直接分析持仓/关注标的 |
| `/stj ah prompt` | 试用 analyze_holdings 组合分析提示词 |
| `/stj ah prompt RDDT.US` | 试用 analyze_holdings 单股分析提示词 |
| `/stj ah prompt 腾讯` | 试用关注标的买入候选分析提示词 |
| `/stj ah quick RDDT.US` | 试用 analyze_holdings 快速分析提示词 |
| `/stj ah tasks` | 试用 analyze_holdings 分析任务清单 |
| `/stj analyze_hoding prompt` | `analyze_holdings` 拼写容错别名 |
| `/stj tv link RDDT.US` | 试用 TradingView 链接 |
| `/stj tv report` | 试用 TradingView 持仓报告 |
| `/stj tv open RDDT.US` | 打开 TradingView 单股图表 |
| `/stj 看图 RDDT.US` | 生成带交易/关注标注的本地图表 |
| `/stj 同步IBKR` | 同步盈透数据 |

## 处理用户请求

收到用户请求后，根据意图执行对应操作：

### 记录交易
```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 record_trade.py --ts-code <代码> --side <BUY/SELL> --price <价格> --quantity <数量>
```

### 查看持仓
```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 query_positions.py
```

### 管理关注列表
```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 watchlist.py <add/ls/rm/up> [参数]
```

### 记录关注笔记
```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 watchlist.py note <代码> --note <笔记>
```

关注列表和关注记录分开：关注列表表示标的状态，关注记录是类似交易记录的观察笔记，没有买卖方向、数量和价格。

### ah 直接分析
当用户说 `/stj ah <标的>分析`、`/stj ah analyze <标的>`、`/stj 分析 <标的>`、`/stj 看看 <标的>`、`买不买/持有吗` 时，直接分析，不要只输出 prompt。

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

### analyze_holdings 提示词
```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 analyze_holdings.py prompt
cd ~/.claude/skills/stock-trade-journal/scripts && python3 analyze_holdings.py prompt <代码>
cd ~/.claude/skills/stock-trade-journal/scripts && python3 analyze_holdings.py quick <代码>
cd ~/.claude/skills/stock-trade-journal/scripts && python3 analyze_holdings.py context <代码或名称> --json
cd ~/.claude/skills/stock-trade-journal/scripts && python3 analyze_holdings.py tasks
```

触发规则：
- `/stj ah prompt`、`/stj analyze_holdings prompt`、`/stj 分析持仓`：生成组合分析提示词。
- `/stj ah prompt <代码或名称>`、`/stj analyze_holdings <代码或名称>`：生成单股分析提示词；若参数里带“分析/看看/买不买/持有吗”，则按直接分析处理。
- `/stj ah <代码或名称>分析`、`/stj ah prompt <代码或名称>分析`、`/stj ah analyze <代码或名称>`：直接分析，先跑 `context`，再按 `references/invest-research-flow.md` 输出结论。
- `/stj analyze_hoding ...`：按 `analyze_holdings` 处理，用于拼写容错。
- `/stj ah quick <代码或名称>`、`/stj 快速分析 <代码或名称>`：生成快速分析提示词。
- `/stj ah tasks`、`/stj 分析任务`：生成分析任务清单。

只有用户显式使用 `prompt` 且没有“分析/看看/买不买/持有吗”等分析意图时，才直接把脚本输出给用户；用户说“分析”时必须直接产出分析结论。

### TradingView 辅助分析
```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 analyze_positions.py link
cd ~/.claude/skills/stock-trade-journal/scripts && python3 analyze_positions.py link --ts-code <代码>
cd ~/.claude/skills/stock-trade-journal/scripts && python3 analyze_positions.py report
cd ~/.claude/skills/stock-trade-journal/scripts && python3 analyze_positions.py tv --ts-code <代码>
```

触发规则：
- `/stj tv link`、`/stj tradingview link`：输出所有持仓 TradingView 链接。
- `/stj tv link <代码>`：输出单股 TradingView 链接。
- `/stj tv report`、`/stj tradingview report`：生成持仓报告。
- `/stj tv open <代码>`、`/stj 打开 TradingView <代码>`：打开单股 TradingView 图表。
- `/stj tv open all`：打开所有当前持仓图表。

这是 TradingView 链接/报告工作流，和 `analyze_holdings.py` 的提示词工作流分开处理。

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
