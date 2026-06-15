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
import re
from datetime import datetime
from typing import Any, Optional

from db_schema import get_notes, get_trade_decision_note, ensure_db, get_positions


IMPORT_MARKERS = (
    "IBKR PDF import",
    "source_pdf=",
    "account=",
    "settlement=",
    "listing_exchange=",
    "proceeds=",
    "commission=",
    "fee=",
)


def clean_user_note(value: Any) -> str:
    """过滤导入来源等元数据，避免误当成投资笔记。"""
    text = str(value or "").strip()
    if not text:
        return ""
    if any(marker in text for marker in IMPORT_MARKERS):
        return ""
    return text


def normalize_query(query: str) -> str:
    """把自然语言片段规整成更容易匹配的代码或名称。"""
    q = (query or "").strip()
    for word in ("分析一下", "分析", "研究一下", "研究", "看看", "看一下"):
        q = q.replace(word, "")
    q = q.strip().strip(":：,，")
    if re.fullmatch(r"[A-Za-z]{1,8}", q):
        return f"{q.upper()}.US"
    return q


def get_recent_trades(conn, ts_code: str, limit: int = 10) -> list[dict[str, Any]]:
    """读取最近交易记录。"""
    cursor = conn.execute(
        """
        SELECT id, ts_code, exchange, side, price, quantity, stop_loss,
               take_profit, note, timestamp, source, commission, currency
        FROM trades
        WHERE ts_code = ?
        ORDER BY timestamp DESC, id DESC
        LIMIT ?
        """,
        (ts_code, limit),
    )
    trades = []
    for row in cursor.fetchall():
        item = dict(row)
        canonical_note = get_trade_decision_note(conn, item["id"])
        item["note"] = clean_user_note(canonical_note or item.get("note"))
        trades.append(item)
    return trades


def resolve_target(
    conn,
    positions: list[dict[str, Any]],
    query: str,
) -> tuple[str, Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """按代码、名称或自然语言片段解析标的。"""
    normalized = normalize_query(query)
    candidates = [query, normalized]
    for candidate in candidates:
        pos = next((p for p in positions if p["ts_code"].upper() == candidate.upper()), None)
        if pos:
            return pos["ts_code"], pos, find_watch(conn, pos["ts_code"])

    for candidate in candidates:
        watch = find_watch(conn, candidate)
        if watch:
            pos = next((p for p in positions if p["ts_code"] == watch["ts_code"]), None)
            return watch["ts_code"], pos, watch

    return normalized, None, None


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


def generate_watch_analysis_prompt(
    watch: dict[str, Any],
    notes: list[dict[str, Any]],
    analysis_type: str = "fundamental",
) -> str:
    """生成关注标的的买入候选分析提示词。"""
    ts_code = watch["ts_code"]
    name = watch.get("name") or ""
    title = f"{name}（{ts_code}）" if name else ts_code
    target = watch.get("target_price")
    stop = watch.get("stop_loss")
    category = watch.get("category") or "default"

    watch_lines = [
        f"- 分类: {category}",
        "- 当前状态: 关注中，尚无本地持仓",
        "- 分析目标: 判断是否值得新开仓买入，以及需要等待的买入触发条件",
    ]
    if target:
        watch_lines.append(f"- 目标价: {target}")
    if stop:
        watch_lines.append(f"- 止损价: {stop}")

    note_lines = []
    for item in notes[:5]:
        ts = (item.get("timestamp") or "")[:10]
        item_note = item.get("note") or ""
        if item_note:
            note_lines.append(f"- {ts}: {item_note}")
    notes_text = "\n".join(note_lines) if note_lines else "- 暂无关注记录"

    if analysis_type == "quick":
        return f"""快速分析买入候选 {title}：

## 关注信息
{chr(10).join(watch_lines)}

## 最近关注记录
{notes_text}

请简要回答：
1. 现在能不能买？如果不能，差在哪个确认条件？
2. “疑似触底/反弹”这一观察是否有价格、成交量或趋势数据支撑？
3. 合理的买入触发条件是什么？
4. 买入后应如何设置止损/失效条件？
"""

    return f"""请使用 invest-research-skills 的 stock-fundamental + tradingview-quantitative 框架分析买入候选 {title}：

## 关注信息
{chr(10).join(watch_lines)}

## 最近关注记录
{notes_text}

## 分析要求
1. 基本面：业务模式、盈利来源、竞争格局、财务质量
2. 技术面：趋势位置、支撑/压力、成交量、是否具备触底反弹确认
3. 买入判断：当前是否可以买；如果不买，需要等待什么条件
4. 交易计划：候选买入区间、分批方式、止损/失效位置、跟踪目标
5. 风险与失效：哪些变化说明买入假设失效
6. 跟踪清单：后续需要关注的价格、财报、行业或事件指标

请给出具体数据支撑的结论，不要空泛描述。
"""


def find_watch(conn, query: str) -> Optional[dict[str, Any]]:
    """按代码或名称查找关注标的。"""
    row = conn.execute(
        """
        SELECT * FROM watchlist
        WHERE status != 'removed'
          AND (ts_code = ? OR name = ? OR name LIKE ?)
        ORDER BY priority DESC, updated_at DESC
        LIMIT 1
        """,
        (query, query, f"%{query}%"),
    ).fetchone()
    return dict(row) if row else None


def get_watch_notes(conn, ts_code: str, limit: int = 20) -> list[dict[str, Any]]:
    """读取统一标的笔记。保留旧函数名以兼容内部调用。"""
    return get_notes(conn, ts_code, limit=limit)


def get_watchlist(conn, status: str = "watching") -> list[dict[str, Any]]:
    """读取关注列表。"""
    cursor = conn.execute(
        """
        SELECT *
        FROM watchlist
        WHERE status = ?
        ORDER BY priority DESC, added_at DESC, id DESC
        """,
        (status,),
    )
    return [dict(row) for row in cursor.fetchall()]


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


def build_watchlist_context_packet(
    conn,
    positions: list[dict[str, Any]],
    notes_limit: int = 10,
) -> dict[str, Any]:
    """生成关注池分析上下文。"""
    positions_by_code = {pos["ts_code"]: pos for pos in positions}
    watches = []
    for watch in get_watchlist(conn):
        ts_code = watch["ts_code"]
        notes = get_watch_notes(conn, ts_code, limit=notes_limit)
        trades = get_recent_trades(conn, ts_code, limit=10)
        position = positions_by_code.get(ts_code)
        watches.append(
            {
                "ts_code": ts_code,
                "mode": "holding" if position else "watch_candidate",
                "watch": watch,
                "notes": notes,
                "position": position,
                "recent_trades": trades,
            }
        )
    return {
        "mode": "watchlist",
        "count": len(watches),
        "watches": watches,
        "analysis_contract": "分析整个关注池的优先级、买入触发条件、事件风险和后续跟踪清单",
        "required_framework": [
            "先给关注池排序和动作结论",
            "逐个标的结合关注笔记说明当前假设",
            "区分基本面验证、技术面确认、事件落地三类触发条件",
            "给出每个标的可观察的失效条件",
            "最后输出下次复盘要看的数据/价格/公告",
        ],
        "framework_refs": [
            "references/invest-research-flow.md",
            "references/invest-research-skills/stock-fundamental/SKILL.md",
            "references/invest-research-skills/sector-research/SKILL.md",
            "references/invest-research-skills/shared-research-context/references/research-methodology.md",
            "references/invest-research-skills/shared-research-context/references/data-quality-levels.md",
            "references/invest-research-skills/shared-research-context/references/external-factors.md",
            "references/invest-research-skills/shared-research-context/references/pitfalls.md",
        ],
    }


def build_context_packet(
    conn,
    positions: list[dict[str, Any]],
    query: str,
) -> dict[str, Any]:
    """生成供 agent 直接分析使用的本地上下文包。"""
    resolved_code, position, watch = resolve_target(conn, positions, query)
    notes = get_watch_notes(conn, resolved_code, limit=10)
    trades = get_recent_trades(conn, resolved_code, limit=10)
    mode = "holding" if position else "watch_candidate" if watch else "unknown"
    return {
        "query": query,
        "resolved_code": resolved_code,
        "mode": mode,
        "position": position,
        "watch": watch,
        "notes": notes,
        "recent_trades": trades,
        "analysis_contract": {
            "holding": "分析继续持有、加仓、减仓、风险和失效条件",
            "watch_candidate": "分析是否值得新开仓买入、买入触发条件、仓位计划和失效条件",
            "unknown": "未匹配到本地持仓或关注记录，只能做通用标的研究",
        }.get(mode),
        "required_framework": [
            "先结论后依据",
            "业务模式与盈利来源",
            "竞争对手与相对位置",
            "财务质量验证",
            "外部驱动变量与传导链",
            "估值/交易动作仅在用户请求或本地持仓场景下输出",
            "给出可观察的失效条件和跟踪指标",
        ],
        "framework_refs": [
            "references/invest-research-flow.md",
            "references/invest-research-skills/stock-fundamental/SKILL.md",
            "references/invest-research-skills/stock-fundamental/references/business-model-types.md",
            "references/invest-research-skills/stock-fundamental/references/financial-diagnostics.md",
            "references/invest-research-skills/stock-fundamental/references/competitor-matrix.md",
            "references/invest-research-skills/stock-fundamental/references/profit-transmission.md",
            "references/invest-research-skills/shared-research-context/references/research-methodology.md",
            "references/invest-research-skills/shared-research-context/references/data-quality-levels.md",
            "references/invest-research-skills/shared-research-context/references/moat-framework.md",
            "references/invest-research-skills/shared-research-context/references/lifecycle-framework.md",
            "references/invest-research-skills/sector-research/SKILL.md",
        ],
    }


def print_context_packet(packet: dict[str, Any]) -> None:
    """以人类可读格式输出本地上下文包。"""
    print(f"标的: {packet['resolved_code']}")
    print(f"模式: {packet['mode']}")
    if packet.get("position"):
        pos = packet["position"]
        print("\n持仓:")
        print(f"- 数量: {pos.get('quantity')}")
        print(f"- 均价: {pos.get('avg_cost')}")
        print(f"- 成本: {pos.get('total_cost')}")
        print(f"- 货币: {pos.get('currency')}")
    if packet.get("watch"):
        watch = packet["watch"]
        print("\n关注:")
        print(f"- 名称: {watch.get('name') or '-'}")
        print(f"- 分类: {watch.get('category') or '-'}")
        print(f"- 目标价: {watch.get('target_price') or '-'}")
        print(f"- 止损价: {watch.get('stop_loss') or '-'}")
    if packet.get("notes"):
        print("\n笔记:")
        for note in packet["notes"]:
            print(
                f"- {(note.get('timestamp') or '')[:10]} "
                f"[{note.get('note_type') or '-'}] {note.get('note') or '-'}"
            )
    if packet.get("recent_trades"):
        print("\n最近交易:")
        for trade in packet["recent_trades"]:
            print(
                f"- {(trade.get('timestamp') or '')[:10]} "
                f"{trade.get('side')} {trade.get('quantity')} @ {trade.get('price')}"
            )


def print_watchlist_context_packet(packet: dict[str, Any]) -> None:
    """以人类可读格式输出关注池上下文。"""
    print(f"关注池: {packet.get('count', 0)} 个标的")
    for index, item in enumerate(packet.get("watches") or [], 1):
        watch = item["watch"]
        name = watch.get("name") or "-"
        target = watch.get("target_price") or "-"
        stop = watch.get("stop_loss") or "-"
        print(
            f"\n{index}. {watch['ts_code']} {name} "
            f"| {watch.get('category') or '-'} | 目标 {target} | 止损 {stop} | {item['mode']}"
        )
        notes = item.get("notes") or []
        if notes:
            for note in notes:
                print(
                    f"   - {(note.get('timestamp') or '')[:10]} "
                    f"[{note.get('note_type') or '-'}] {note.get('note') or '-'}"
                )
        else:
            print("   - 暂无笔记")
        if item.get("position"):
            pos = item["position"]
            print(f"   - 持仓: {pos.get('quantity')} @ {pos.get('avg_cost')}")


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
    print("  可用上下文命令:")
    print("-" * 60)
    print("  analyze_holdings.py context <代码> --json    # 单只持仓/关注上下文")
    print("  analyze_holdings.py watchlist --json         # 关注池上下文")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="持仓一键分析工具")
    parser.add_argument("--workspace",
                        default=os.path.expanduser(os.environ.get("STJ_WORKSPACE", "~/.trade-journal")),
                        help="工作目录 (默认: STJ_WORKSPACE 或 ~/.trade-journal)")
    parser.add_argument("command", nargs="?", default="menu",
                        choices=["menu", "prompt", "links", "tasks", "quick", "context", "watchlist"],
                        help="命令")
    parser.add_argument("ts_code", nargs="?", help="股票代码（可选）")
    parser.add_argument("--type", "-t", default="fundamental",
                        choices=["fundamental", "sector", "quick"],
                        help="分析类型")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--notes-limit", type=int, default=10, help="关注池每个标的读取最近 N 条关注记录")
    args = parser.parse_args()

    # 连接数据库
    base = os.path.join(args.workspace, "results", "trade-journal")
    db_path = os.path.join(base, "db", "trades.db")
    conn = ensure_db(db_path)

    # 获取持仓
    positions = get_positions(conn)

    if args.command == "menu":
        print_analysis_menu(positions)

    elif args.command == "prompt":
        if args.ts_code:
            # 单股分析
            resolved_code, pos, watch = resolve_target(conn, positions, args.ts_code)
            if pos:
                prompt = generate_analysis_prompt(pos, args.type)
                print(prompt)
            elif watch:
                notes = get_watch_notes(conn, watch["ts_code"], limit=5)
                prompt = generate_watch_analysis_prompt(watch, notes, args.type)
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
            resolved_code, pos, watch = resolve_target(conn, positions, args.ts_code)
            if pos:
                prompt = generate_analysis_prompt(pos, "quick")
                print(prompt)
            elif watch:
                notes = get_watch_notes(conn, watch["ts_code"], limit=5)
                prompt = generate_watch_analysis_prompt(watch, notes, "quick")
                print(prompt)
            else:
                print(f"未找到持仓或关注标的: {args.ts_code}")
        else:
            for pos in positions:
                print(f"\n### {pos['ts_code']}")
                print(generate_analysis_prompt(pos, "quick"))

    elif args.command == "context":
        if not args.ts_code:
            print("请提供股票代码或名称")
        else:
            packet = build_context_packet(conn, positions, args.ts_code)
            if args.json:
                print(json.dumps(packet, indent=2, ensure_ascii=False))
            else:
                print_context_packet(packet)

    elif args.command == "watchlist":
        packet = build_watchlist_context_packet(conn, positions, notes_limit=args.notes_limit)
        if args.json:
            print(json.dumps(packet, indent=2, ensure_ascii=False))
        else:
            print_watchlist_context_packet(packet)

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

    conn.close()


if __name__ == "__main__":
    main()
