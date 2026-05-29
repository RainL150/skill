#!/usr/bin/env python3
"""
IBKR (Interactive Brokers) 交易记录同步工具

从 IBKR TWS/Gateway 获取交易记录并同步到本地数据库，同时更新持仓表。

依赖：
  pip install ib_insync

使用前提：
  1. 运行 TWS 或 IB Gateway
  2. 启用 API 连接 (Edit > Global Configuration > API > Settings)
  3. 勾选 "Enable ActiveX and Socket Clients"

端口说明：
  - TWS Live: 7496
  - TWS Paper: 7497
  - IB Gateway Live: 4001
  - IB Gateway Paper: 4002
"""

import argparse
import os
from datetime import datetime
from typing import Any

try:
    from ib_insync import IB, util
except ImportError:
    print("错误: 请先安装 ib_insync: pip install ib_insync")
    exit(1)

from db_schema import (
    ensure_db, update_position_after_trade, sync_positions_from_ibkr,
    get_positions, get_position
)
from journal_markdown import append_trade_md


US_EXCHANGES = {"SMART", "NASDAQ", "NYSE", "ARCA", "AMEX", "ISLAND", "BATS", "IEX"}


def get_contract_exchange(contract) -> str:
    """返回用于记录和 TradingView 的交易所。"""
    primary_exchange = getattr(contract, "primaryExchange", None)
    exchange = getattr(contract, "exchange", None)
    if primary_exchange and primary_exchange != "SMART":
        return primary_exchange.upper()
    if exchange and exchange != "SMART":
        return exchange.upper()
    return ""


def convert_symbol(contract) -> str:
    """
    将 IBKR 合约转换为统一代码格式

    Examples:
        - US Stock: AAPL -> AAPL.US
        - HK Stock: 700 -> 0700.HK
        - A Stock (via SEHK connect): 600519 -> 600519.SH
    """
    symbol = contract.symbol
    exchange = get_contract_exchange(contract)
    routing_exchange = (getattr(contract, "exchange", None) or getattr(contract, "primaryExchange", None) or "").upper()
    lookup_exchange = exchange or routing_exchange

    # 美股
    if lookup_exchange in US_EXCHANGES:
        return f"{symbol}.US"
    # 港股
    elif exchange in ('SEHK', 'HKFE'):
        return f"{symbol.zfill(4)}.HK"
    # A股 (通过沪港通/深港通)
    elif exchange in ('SEHKNTL', 'SEHKSZSE'):
        suffix = '.SH' if symbol.startswith('6') else '.SZ'
        return f"{symbol}{suffix}"
    # 其他
    else:
        return f"{symbol}.{exchange}"


def sync_executions(ib: IB, conn, md_base: str, days: int = 7) -> int:
    """
    同步 IBKR 执行记录到本地数据库

    Args:
        ib: IBKR 连接
        conn: SQLite 连接
        md_base: Markdown 文件目录
        days: 同步最近 N 天的记录

    Returns:
        新同步的交易数量
    """
    # 获取执行记录
    executions = ib.executions()

    if not executions:
        print("未找到执行记录")
        return 0

    # 检查已存在的 exec_id
    cursor = conn.execute("SELECT ibkr_exec_id FROM trades WHERE ibkr_exec_id IS NOT NULL")
    existing_ids = set(row[0] for row in cursor.fetchall())

    new_count = 0
    for fill in executions:
        exec_id = fill.execution.execId

        # 跳过已存在的记录
        if exec_id in existing_ids:
            continue

        contract = fill.contract
        execution = fill.execution

        ts_code = convert_symbol(contract)
        exchange = get_contract_exchange(contract)
        side = "BUY" if execution.side == "BOT" else "SELL"
        price = execution.avgPrice
        quantity = int(execution.shares)
        amount = price * quantity
        timestamp = execution.time.isoformat() if execution.time else datetime.now().isoformat()

        # 获取佣金信息
        commission = fill.commissionReport.commission if fill.commissionReport else None
        currency = contract.currency

        # 获取交易前持仓
        pos_before = get_position(conn, ts_code)
        position_before = pos_before["quantity"] if pos_before else 0

        # 计算交易后持仓
        if side == "BUY":
            position_after = position_before + quantity
        else:
            position_after = position_before - quantity

        row: dict[str, Any] = {
            "ts_code": ts_code,
            "exchange": exchange,
            "side": side,
            "price": price,
            "quantity": quantity,
            "amount": amount,
            "position_before": position_before,
            "position_after": position_after,
            "reason": f"IBKR Order #{execution.orderId}",
            "stop_loss": None,
            "take_profit": None,
            "note": f"Account: {execution.acctNumber}",
            "timestamp": timestamp,
            "source": "ibkr",
            "ibkr_exec_id": exec_id,
            "ibkr_order_id": execution.orderId,
            "commission": commission,
            "currency": currency,
        }

        # 写入交易记录
        conn.execute("""
            INSERT INTO trades(
                ts_code, exchange, side, price, quantity, amount,
                position_before, position_after, reason, stop_loss, take_profit,
                note, timestamp, source, ibkr_exec_id, ibkr_order_id, commission, currency
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            row["ts_code"], row["exchange"], row["side"], row["price"], row["quantity"],
            row["amount"], row["position_before"], row["position_after"], row["reason"],
            row["stop_loss"], row["take_profit"], row["note"], row["timestamp"],
            row["source"], row["ibkr_exec_id"], row["ibkr_order_id"],
            row["commission"], row["currency"]
        ))

        # 更新持仓表
        update_position_after_trade(conn, row)

        # 写入 Markdown
        md_path = os.path.join(md_base, f"{ts_code}.md")
        append_trade_md(md_path, row)

        new_count += 1
        print(f"  同步: {ts_code} {side} {quantity} @ {price}")

    conn.commit()
    return new_count


def fetch_ibkr_positions(ib: IB) -> list[dict[str, Any]]:
    """获取 IBKR 当前持仓"""
    positions = ib.positions()
    result = []
    for pos in positions:
        ts_code = convert_symbol(pos.contract)
        result.append({
            "ts_code": ts_code,
            "exchange": get_contract_exchange(pos.contract),
            "quantity": int(pos.position),
            "avg_cost": pos.avgCost,
            "market_value": getattr(pos, 'marketValue', None),
            "account": pos.account,
            "currency": pos.contract.currency,
        })
    return result


def print_positions_table(positions: list[dict[str, Any]], source: str = "") -> None:
    """打印持仓表格"""
    if not positions:
        print("  无持仓")
        return

    print(f"\n{'='*70}")
    print(f"  {'代码':<12} {'交易所':<10} {'数量':>10} {'均价':>12} {'市值':>12} {'货币':<6}")
    print(f"{'='*70}")

    for pos in positions:
        qty = pos.get('quantity', 0)
        if qty == 0:
            continue
        avg_cost = pos.get('avg_cost') or pos.get('avg_cost', 0)
        market_value = pos.get('market_value') or pos.get('market_value', '-')
        currency = pos.get('currency', 'USD')
        exchange = pos.get('exchange') or '-'

        mv_str = f"{market_value:,.2f}" if isinstance(market_value, (int, float)) else str(market_value)
        print(f"  {pos['ts_code']:<12} {exchange:<10} {qty:>10,} {avg_cost:>12.2f} {mv_str:>12} {currency:<6}")

    print(f"{'='*70}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="IBKR 交易记录同步工具")
    parser.add_argument("--workspace", required=True, help="工作目录")
    parser.add_argument("--host", default="127.0.0.1", help="TWS/Gateway 主机 (默认: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=7497, help="TWS/Gateway 端口 (默认: 7497 Paper Trading)")
    parser.add_argument("--client-id", type=int, default=1, help="客户端 ID (默认: 1)")
    parser.add_argument("--days", type=int, default=7, help="同步最近 N 天的记录 (默认: 7)")
    parser.add_argument("--positions", action="store_true", help="显示当前持仓")
    parser.add_argument("--sync-positions", action="store_true", help="同步 IBKR 持仓到本地数据库")
    parser.add_argument("--readonly", action="store_true", help="只读模式，只显示不写入")
    parser.add_argument("--local", action="store_true", help="显示本地数据库持仓")
    args = parser.parse_args()

    base = os.path.join(args.workspace, "results", "trade-journal")
    db_path = os.path.join(base, "db", "trades.db")
    md_base = os.path.join(base, "records")

    # 如果只查看本地数据库
    if args.local:
        conn = ensure_db(db_path)
        print("\n=== 本地数据库持仓 ===")
        local_positions = get_positions(conn)
        print_positions_table(local_positions, "本地")
        conn.close()
        return

    print(f"连接到 IBKR TWS/Gateway ({args.host}:{args.port})...")

    ib = IB()
    try:
        ib.connect(args.host, args.port, clientId=args.client_id, readonly=True)
        print(f"已连接! 账户: {ib.managedAccounts()}")

        # 获取 IBKR 持仓
        ibkr_positions = fetch_ibkr_positions(ib)

        if args.positions:
            print("\n=== IBKR 当前持仓 ===")
            print_positions_table(ibkr_positions, "IBKR")

        if not args.readonly:
            conn = ensure_db(db_path)

            # 同步持仓到本地数据库
            if args.sync_positions and ibkr_positions:
                print("\n=== 同步持仓到本地数据库 ===")
                sync_positions_from_ibkr(conn, ibkr_positions)
                print(f"  已同步 {len(ibkr_positions)} 个持仓")

            # 同步执行记录
            print(f"\n=== 同步执行记录 (最近 {args.days} 天) ===")
            new_count = sync_executions(ib, conn, md_base, args.days)

            print(f"\n同步完成! 新增 {new_count} 条交易记录")

            # 显示本地数据库持仓
            print("\n=== 本地数据库持仓 ===")
            local_positions = get_positions(conn)
            print_positions_table(local_positions, "本地")

            conn.close()
            print(f"数据库: {db_path}")
            print(f"Markdown: {md_base}/")
        else:
            print("\n只读模式，跳过同步")

    except Exception as e:
        print(f"错误: {e}")
        print("\n请确保:")
        print("  1. TWS 或 IB Gateway 正在运行")
        print("  2. API 连接已启用 (Edit > Global Configuration > API > Settings)")
        print("  3. 端口号正确 (TWS Paper: 7497, TWS Live: 7496)")
        exit(1)
    finally:
        ib.disconnect()


if __name__ == "__main__":
    main()
