#!/usr/bin/env python3
"""
持仓一键分析工具 - 集成 invest-research-skills

功能:
1. 读取当前持仓
2. 生成分析提示词（可直接发送给 AI）
3. 批量生成 TradingView 链接
4. 输出分析任务清单
"""

import argparse
import json
import os
from datetime import datetime
from typing import Any

from db_schema import ensure_db, get_positions


def generate_analysis_prompt(position: dict[str, Any], analysis_type: str = "fundamental") -> str:
    """生成单个股票的分析提示词"""
    ts_code = position["ts_code"]
    quantity = position.get("quantity", 0)
    avg_cost = position.get("avg_cost", 0)
    currency = position.get("currency", "USD")

    if analysis_type == "fundamental":
        return f"""请使用 invest-research-skills 的 stock-fundamental 框架分析 {ts_code}：

持仓信息：
- 持仓数量: {quantity}
- 持仓均价: {avg_cost:.2f} {currency}
- 持仓成本: {avg_cost * quantity:.2f} {currency}

分析要求：
1. 业务模式与盈利来源
2. 竞争对手与相对位置
3. 财务质量验证
4. 外部驱动变量与传导链
5. 核心风险与失效条件
6. 需持续跟踪的关键指标

请给出具体数据支撑的结论，不要空泛描述。"""

    elif analysis_type == "sector":
        return f"""请使用 invest-research-skills 的 sector-research 框架分析 {ts_code} 所在行业：

分析要求：
1. 行业生命周期阶段判断
2. 市场规模与增速
3. 竞争格局与集中度
4. 产业链分析
5. 景气度与拐点信号
6. 政策与风险因素"""

    elif analysis_type == "quick":
        return f"""快速分析 {ts_code}：

持仓: {quantity} 股 @ {avg_cost:.2f} {currency}

请简要回答：
1. 当前基本面是否支持继续持有？
2. 有无明显风险信号？
3. 建议的跟踪指标是什么？"""

    return f"分析 {ts_code}"


def generate_batch_analysis_prompt(positions: list[dict[str, Any]]) -> str:
    """生成批量分析提示词"""
    if not positions:
        return "无持仓数据"

    holdings_list = []
    total_cost = 0

    for pos in positions:
        ts_code = pos["ts_code"]
        qty = pos.get("quantity", 0)
        avg_cost = pos.get("avg_cost", 0)
        cost = avg_cost * qty
        total_cost += cost
        currency = pos.get("currency", "USD")
        holdings_list.append(f"- {ts_code}: {qty} 股 @ {avg_cost:.2f} {currency} (成本 {cost:,.0f})")

    holdings_str = "\n".join(holdings_list)

    return f"""请分析我的持仓组合：

## 当前持仓
{holdings_str}

总成本: {total_cost:,.0f}

## 分析要求

### 1. 组合概览
- 行业分布是否合理
- 集中度风险评估
- 相关性分析

### 2. 逐一分析（每只股票简要）
对每只持仓股票，给出：
- 当前基本面判断（1-2句话）
- 主要风险点
- 建议动作（持有/减仓/加仓/观察）

### 3. 组合建议
- 需要关注的风险
- 建议的调整方向
- 近期需跟踪的关键事件/数据

请基于最新数据分析，给出具体、可操作的建议。"""


def generate_tradingview_links(positions: list[dict[str, Any]]) -> list[dict[str, str]]:
    """生成 TradingView 链接"""
    links = []

    for pos in positions:
        ts_code = pos["ts_code"]
        parts = ts_code.rsplit('.', 1)

        if len(parts) == 2:
            symbol, market = parts
            market = market.upper()

            tv_symbol = ""
            if market == "US":
                tv_symbol = f"NASDAQ:{symbol}"
            elif market == "HK":
                tv_symbol = f"HKEX:{symbol.zfill(4)}"
            elif market == "SH":
                tv_symbol = f"SSE:{symbol}"
            elif market == "SZ":
                tv_symbol = f"SZSE:{symbol}"
            else:
                tv_symbol = f"{market}:{symbol}"

            links.append({
                "ts_code": ts_code,
                "tv_symbol": tv_symbol,
                "url": f"https://www.tradingview.com/chart/?symbol={tv_symbol}"
            })

    return links


def print_analysis_menu(positions: list[dict[str, Any]]):
    """打印分析菜单"""
    print("\n" + "=" * 60)
    print("  持仓分析工具")
    print("=" * 60)

    if not positions:
        print("  无持仓数据")
        return

    print(f"\n  当前持仓 ({len(positions)} 只):\n")
    for i, pos in enumerate(positions, 1):
        ts_code = pos["ts_code"]
        qty = pos.get("quantity", 0)
        avg_cost = pos.get("avg_cost", 0)
        print(f"  {i}. {ts_code:<12} {qty:>8} 股 @ {avg_cost:>10.2f}")

    print("\n" + "-" * 60)
    print("  可用分析命令:")
    print("-" * 60)
    print("  analyze_holdings.py prompt          # 生成组合分析提示词")
    print("  analyze_holdings.py prompt <代码>   # 生成单股分析提示词")
    print("  analyze_holdings.py links           # 生成 TradingView 链接")
    print("  analyze_holdings.py tasks           # 生成分析任务清单")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="持仓一键分析工具")
    parser.add_argument("--workspace",
                        default=os.path.expanduser(os.environ.get("STJ_WORKSPACE", "~/.trade-journal")),
                        help="工作目录 (默认: STJ_WORKSPACE 或 ~/.trade-journal)")
    parser.add_argument("command", nargs="?", default="menu",
                        choices=["menu", "prompt", "links", "tasks", "quick"],
                        help="命令")
    parser.add_argument("ts_code", nargs="?", help="股票代码（可选）")
    parser.add_argument("--type", "-t", default="fundamental",
                        choices=["fundamental", "sector", "quick"],
                        help="分析类型")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    # 连接数据库
    base = os.path.join(args.workspace, "results", "trade-journal")
    db_path = os.path.join(base, "db", "trades.db")
    conn = ensure_db(db_path)

    # 获取持仓
    positions = get_positions(conn)
    conn.close()

    if args.command == "menu":
        print_analysis_menu(positions)

    elif args.command == "prompt":
        if args.ts_code:
            # 单股分析
            pos = next((p for p in positions if p["ts_code"] == args.ts_code), None)
            if pos:
                prompt = generate_analysis_prompt(pos, args.type)
                print(prompt)
            else:
                print(f"未找到持仓: {args.ts_code}")
        else:
            # 组合分析
            prompt = generate_batch_analysis_prompt(positions)
            print(prompt)

    elif args.command == "quick":
        # 快速分析提示词
        if args.ts_code:
            pos = next((p for p in positions if p["ts_code"] == args.ts_code), None)
            if pos:
                prompt = generate_analysis_prompt(pos, "quick")
                print(prompt)
        else:
            for pos in positions:
                print(f"\n### {pos['ts_code']}")
                print(generate_analysis_prompt(pos, "quick"))

    elif args.command == "links":
        links = generate_tradingview_links(positions)
        if args.json:
            print(json.dumps(links, indent=2, ensure_ascii=False))
        else:
            print("\nTradingView 链接:\n")
            for link in links:
                print(f"  {link['ts_code']:<12} → {link['url']}")
            print()

    elif args.command == "tasks":
        print("\n分析任务清单:\n")
        print("=" * 60)
        for i, pos in enumerate(positions, 1):
            ts_code = pos["ts_code"]
            print(f"\n[ ] {i}. {ts_code}")
            print(f"    - [ ] 基本面分析 (stock-fundamental)")
            print(f"    - [ ] 行业分析 (sector-research)")
            print(f"    - [ ] 技术面检查 (tradingview-quantitative)")
            print(f"    - [ ] 更新目标价/止损价")
        print("\n" + "=" * 60)
        print(f"\n总计: {len(positions)} 只股票待分析\n")


if __name__ == "__main__":
    main()
