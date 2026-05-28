#!/usr/bin/env python3
"""
手动记录交易 - 同时更新交易表和持仓表
"""

import argparse
import os
from datetime import datetime

from db_schema import ensure_db, update_position_after_trade, get_position


def append_md(md_path: str, row: dict):
    """追加交易记录到 Markdown 文件"""
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    if not os.path.exists(md_path):
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# {row['ts_code']} 交易记录\n\n")
    with open(md_path, "a", encoding="utf-8") as f:
        f.write(
            f"## {row['timestamp']} | {row['side']} | {row['ts_code']}\n"
            f"- 价格：{row['price']}\n"
            f"- 数量：{row['quantity']}\n"
            f"- 金额：{row.get('amount', row['price'] * row['quantity']):.2f}\n"
            f"- 交易后持仓：{row.get('position_after', '')}\n"
            f"- 仓位变化：{row.get('position_before', '')} -> {row.get('position_after', '')}\n"
            f"- 触发原因：{row.get('reason', '')}\n"
            f"- 止损：{row.get('stop_loss', '')}\n"
            f"- 止盈：{row.get('take_profit', '')}\n"
            f"- 备注：{row.get('note', '')}\n\n"
        )


def main():
    p = argparse.ArgumentParser(description="记录交易并更新持仓")
    p.add_argument("--workspace", required=True, help="工作目录")
    p.add_argument("--ts-code", required=True, help="股票代码 (如 603067.SH, AAPL.US)")
    p.add_argument("--side", required=True, choices=["BUY", "SELL", "buy", "sell"], help="交易方向")
    p.add_argument("--price", type=float, required=True, help="成交价格")
    p.add_argument("--quantity", type=int, required=True, help="成交数量")
    p.add_argument("--reason", default="", help="交易原因")
    p.add_argument("--stop-loss", type=float, help="止损价")
    p.add_argument("--take-profit", default="", help="止盈目标")
    p.add_argument("--note", default="", help="备注")
    p.add_argument("--currency", default="CNY", help="货币 (默认 CNY)")
    p.add_argument("--timestamp", default=datetime.now().astimezone().isoformat(timespec="seconds"),
                   help="交易时间 (默认当前时间)")
    args = p.parse_args()

    base = os.path.join(args.workspace, "results", "trade-journal")
    db_path = os.path.join(base, "db", "trades.db")
    md_path = os.path.join(base, "records", f"{args.ts_code}.md")

    # 连接数据库
    conn = ensure_db(db_path)

    # 获取交易前持仓
    pos_before = get_position(conn, args.ts_code)
    position_before = pos_before["quantity"] if pos_before else 0

    # 计算交易后持仓
    side = args.side.upper()
    if side == "BUY":
        position_after = position_before + args.quantity
    else:
        position_after = position_before - args.quantity

    # 构建交易记录
    row = {
        "ts_code": args.ts_code,
        "side": side,
        "price": args.price,
        "quantity": args.quantity,
        "amount": args.price * args.quantity,
        "position_before": position_before,
        "position_after": position_after,
        "reason": args.reason,
        "stop_loss": args.stop_loss,
        "take_profit": args.take_profit,
        "note": args.note,
        "timestamp": args.timestamp,
        "source": "manual",
        "currency": args.currency,
    }

    # 写入交易记录
    conn.execute("""
        INSERT INTO trades(
            ts_code, side, price, quantity, amount,
            position_before, position_after, reason, stop_loss, take_profit,
            note, timestamp, source, currency
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        row["ts_code"], row["side"], row["price"], row["quantity"], row["amount"],
        row["position_before"], row["position_after"], row["reason"],
        row["stop_loss"], row["take_profit"], row["note"], row["timestamp"],
        row["source"], row["currency"]
    ))
    conn.commit()

    # 更新持仓表
    update_position_after_trade(conn, row)

    # 获取更新后的持仓
    pos_after = get_position(conn, args.ts_code)

    # 写入 Markdown
    append_md(md_path, row)

    conn.close()

    # 输出结果
    print(f"✅ 交易已记录: {row['ts_code']} {row['side']} {row['quantity']} @ {row['price']}")
    print(f"   金额: {row['amount']:.2f} {row['currency']}")
    print(f"   持仓变化: {position_before} -> {position_after}")
    if pos_after:
        print(f"   当前均价: {pos_after['avg_cost']:.4f}" if pos_after['avg_cost'] else "")
        print(f"   已实现盈亏: {pos_after['realized_pnl']:.2f}" if pos_after['realized_pnl'] else "")


if __name__ == "__main__":
    main()
