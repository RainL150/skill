#!/usr/bin/env python3
"""
手动记录交易 - 同时更新交易表和持仓表
"""

import argparse
import os
from datetime import datetime
from typing import Any

from db_schema import ensure_db, get_position, parse_ts_code, update_position_after_trade
from journal_markdown import append_trade_md


def main() -> None:
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
    p.add_argument("--exchange", help="交易所 (如 NASDAQ, NYSE, HKEX, SSE, SZSE)")
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
    exchange = args.exchange or parse_ts_code(args.ts_code)[2]
    row: dict[str, Any] = {
        "ts_code": args.ts_code,
        "exchange": exchange,
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
            ts_code, exchange, side, price, quantity, amount,
            position_before, position_after, reason, stop_loss, take_profit,
            note, timestamp, source, currency
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        row["ts_code"], row["exchange"], row["side"], row["price"], row["quantity"],
        row["amount"], row["position_before"], row["position_after"], row["reason"],
        row["stop_loss"], row["take_profit"], row["note"], row["timestamp"],
        row["source"], row["currency"]
    ))
    conn.commit()

    # 更新持仓表
    update_position_after_trade(conn, row)

    # 获取更新后的持仓
    pos_after = get_position(conn, args.ts_code)

    # 写入 Markdown
    append_trade_md(md_path, row)

    conn.close()

    # 输出结果
    print(f"✅ 交易已记录: {row['ts_code']} {row['side']} {row['quantity']} @ {row['price']}")
    print(f"   交易所: {row['exchange'] or '-'}")
    print(f"   金额: {row['amount']:.2f} {row['currency']}")
    print(f"   持仓变化: {position_before} -> {position_after}")
    if pos_after:
        if pos_after.get("avg_cost"):
            print(f"   当前均价: {pos_after['avg_cost']:.4f}")
        if pos_after.get("realized_pnl"):
            print(f"   已实现盈亏: {pos_after['realized_pnl']:.2f}")


if __name__ == "__main__":
    main()
