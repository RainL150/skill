#!/usr/bin/env python3
"""Markdown writing helpers for trade journal records."""

import os
from typing import Any


def append_trade_md(md_path: str, row: dict[str, Any]) -> None:
    """追加交易记录到 Markdown 文件"""
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    if not os.path.exists(md_path):
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# {row['ts_code']} 交易记录\n\n")

    exchange = row.get("exchange") or "-"
    commission = row.get("commission")
    commission_text = commission if commission is not None else "N/A"

    with open(md_path, "a", encoding="utf-8") as f:
        f.write(
            f"## {row['timestamp']} | {row['side']} | {row['ts_code']}\n"
            f"- 交易所：{exchange}\n"
            f"- 价格：{row['price']}\n"
            f"- 数量：{row['quantity']}\n"
            f"- 金额：{row.get('amount', row['price'] * row['quantity']):.2f}\n"
            f"- 仓位变化：{row.get('position_before', '')} -> {row.get('position_after', '')}\n"
            f"- 佣金：{commission_text}\n"
            f"- 货币：{row.get('currency', 'N/A')}\n"
            f"- 来源：{row.get('source', 'manual')}\n"
            f"- 触发原因：{row.get('reason', '')}\n"
            f"- 止损：{row.get('stop_loss', '')}\n"
            f"- 止盈：{row.get('take_profit', '')}\n"
            f"- 备注：{row.get('note', '')}\n\n"
        )
