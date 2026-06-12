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
| `/stj 分析持仓` | 一键分析所有持仓 |
| `/stj 分析 RDDT.US` | 分析单只股票 |
| `/stj 看图 RDDT.US` | 生成带交易/关注标注的本地图表 |
| `/stj 同步IBKR` | 同步盈透数据 |
| `/stj web` | 启动 Web 界面 |

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

### 一键分析持仓
```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 analyze_holdings.py prompt
```

然后将生成的提示词用于分析，结合 `invest-research-skills` 框架。

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

### 启动 Web
```bash
cd ~/.claude/skills/stock-trade-journal/web && python3 app.py
```

## 完整功能

完整功能文档见 `/stock-trade-journal`。
