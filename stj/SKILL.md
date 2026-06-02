---
name: stj
description: stock-trade-journal 快捷入口。交易记录、持仓管理、关注列表、一键分析。
---

# /stj - 交易日志快捷命令

这是 `stock-trade-journal` 的快捷别名。

## 使用方式

直接在 `/stj` 后面跟命令即可：

| 命令 | 功能 |
|------|------|
| `/stj 记录 NVDA.US 买入50股@130` | 记录交易 |
| `/stj 持仓` | 查看持仓 |
| `/stj 关注 AVGO.US` | 添加关注 |
| `/stj 关注列表` | 查看关注列表 |
| `/stj 分析持仓` | 一键分析所有持仓 |
| `/stj 分析 RDDT.US` | 分析单只股票 |
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

### 一键分析持仓
```bash
cd ~/.claude/skills/stock-trade-journal/scripts && python3 analyze_holdings.py prompt
```

然后将生成的提示词用于分析，结合 `invest-research-skills` 框架。

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
