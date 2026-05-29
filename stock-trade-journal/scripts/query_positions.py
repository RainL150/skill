#!/usr/bin/env python3
"""
查询持仓信息
"""

import argparse
import os
from typing import Any

from db_schema import ensure_db, get_positions, get_position


def print_positions_table(positions: list[dict[str, Any]]) -> None:
    """打印持仓表格"""
    if not positions:
        print("无持仓记录")
        return

    print(f"\n{'='*90}")
    print(f"  {'代码':<12} {'交易所':<10} {'数量':>10} {'均价':>10} {'总成本':>12} {'已实现盈亏':>12} {'最后交易':<12}")
    print(f"{'='*90}")

    total_cost = 0
    total_realized_pnl = 0

    for pos in positions:
        qty = pos.get('quantity', 0)
        avg_cost = pos.get('avg_cost') or 0
        cost = pos.get('total_cost') or 0
        realized_pnl = pos.get('realized_pnl') or 0
        last_date = pos.get('last_trade_date', '')[:10] if pos.get('last_trade_date') else '-'
        exchange = pos.get('exchange') or '-'

        total_cost += cost
        total_realized_pnl += realized_pnl

        pnl_str = f"{realized_pnl:+,.2f}" if realized_pnl else "0.00"
        qty_str = f"{qty:,}" if qty != 0 else "0 (已清仓)"

        print(f"  {pos['ts_code']:<12} {exchange:<10} {qty_str:>10} {avg_cost:>10.2f} {cost:>12,.2f} {pnl_str:>12} {last_date:<12}")

    print(f"{'='*90}")
    print(f"  {'合计':<12} {'':<10} {'':<10} {total_cost:>12,.2f} {total_realized_pnl:>+12,.2f}")
    print(f"{'='*90}\n")


def print_position_detail(pos: dict[str, Any]) -> None:
    """打印单个持仓详情"""
    print(f"\n{'='*50}")
    print(f"  股票代码: {pos['ts_code']}")
    print(f"  交易所:   {pos.get('exchange') or '-'}")
    print(f"{'='*50}")
    print(f"  当前持仓: {pos['quantity']:,} 股")
    print(f"  平均成本: {pos['avg_cost']:.4f}" if pos['avg_cost'] else "  平均成本: -")
    print(f"  总成本:   {pos['total_cost']:,.2f}" if pos['total_cost'] else "  总成本:   -")
    print(f"  已实现盈亏: {pos['realized_pnl']:+,.2f}" if pos['realized_pnl'] else "  已实现盈亏: 0.00")

    if pos.get('market_price'):
        print(f"  最新市价: {pos['market_price']:.2f}")
    if pos.get('market_value'):
        print(f"  市值:     {pos['market_value']:,.2f}")
    if pos.get('unrealized_pnl'):
        print(f"  未实现盈亏: {pos['unrealized_pnl']:+,.2f}")

    print(f"  货币:     {pos.get('currency', 'CNY')}")
    print(f"  首次买入: {pos['first_buy_date'][:10] if pos.get('first_buy_date') else '-'}")
    print(f"  最后交易: {pos['last_trade_date'][:10] if pos.get('last_trade_date') else '-'}")
    print(f"  更新时间: {pos['updated_at'][:19] if pos.get('updated_at') else '-'}")
    print(f"{'='*50}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="查询持仓信息")
    parser.add_argument("--workspace", required=True, help="工作目录")
    parser.add_argument("--ts-code", help="查询特定股票代码")
    parser.add_argument("--all", action="store_true", help="包含已清仓的股票")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    base = os.path.join(args.workspace, "results", "trade-journal")
    db_path = os.path.join(base, "db", "trades.db")

    if not os.path.exists(db_path):
        print(f"数据库不存在: {db_path}")
        print("请先记录交易或同步 IBKR 数据")
        return

    conn = ensure_db(db_path)

    if args.ts_code:
        # 查询单个股票
        pos = get_position(conn, args.ts_code)
        if pos:
            if args.json:
                import json
                print(json.dumps(pos, indent=2, ensure_ascii=False))
            else:
                print_position_detail(pos)
        else:
            print(f"未找到 {args.ts_code} 的持仓记录")
    else:
        # 查询所有持仓
        positions = get_positions(conn, include_zero=args.all)
        if args.json:
            import json
            print(json.dumps(positions, indent=2, ensure_ascii=False))
        else:
            print_positions_table(positions)

    conn.close()


if __name__ == "__main__":
    main()
