#!/usr/bin/env python3
"""
IBKR (Interactive Brokers) 交易记录同步工具

从 IBKR TWS/Gateway 获取交易记录并同步到本地数据库。

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
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

try:
    from ib_insync import IB, util
except ImportError:
    print("错误: 请先安装 ib_insync: pip install ib_insync")
    exit(1)


def ensure_db(db_path: str) -> sqlite3.Connection:
    """确保数据库和表存在"""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            side TEXT NOT NULL,
            price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            position_before INTEGER,
            position_after INTEGER,
            reason TEXT,
            stop_loss REAL,
            take_profit TEXT,
            note TEXT,
            timestamp TEXT NOT NULL,
            source TEXT DEFAULT 'manual',
            ibkr_exec_id TEXT,
            ibkr_order_id INTEGER,
            commission REAL,
            currency TEXT
        )
    """)
    # 添加新列（如果不存在）
    try:
        conn.execute("ALTER TABLE trades ADD COLUMN source TEXT DEFAULT 'manual'")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE trades ADD COLUMN ibkr_exec_id TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE trades ADD COLUMN ibkr_order_id INTEGER")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE trades ADD COLUMN commission REAL")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE trades ADD COLUMN currency TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    return conn


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
            f"- 佣金：{row.get('commission', 'N/A')}\n"
            f"- 货币：{row.get('currency', 'N/A')}\n"
            f"- 来源：IBKR (execId: {row.get('ibkr_exec_id', 'N/A')})\n"
            f"- 备注：{row.get('note', '')}\n\n"
        )


def convert_symbol(contract) -> str:
    """
    将 IBKR 合约转换为统一代码格式

    Examples:
        - US Stock: AAPL -> AAPL.US
        - HK Stock: 700 -> 0700.HK
        - A Stock (via SEHK connect): 600519 -> 600519.SH
    """
    symbol = contract.symbol
    exchange = contract.exchange or contract.primaryExchange

    # 美股
    if exchange in ('SMART', 'NASDAQ', 'NYSE', 'ARCA', 'AMEX'):
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


def sync_executions(
    ib: IB,
    conn: sqlite3.Connection,
    md_base: str,
    days: int = 7
) -> int:
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
        side = "BUY" if execution.side == "BOT" else "SELL"
        price = execution.avgPrice
        quantity = int(execution.shares)
        timestamp = execution.time.isoformat() if execution.time else datetime.now().isoformat()

        # 获取佣金信息
        commission = fill.commissionReport.commission if fill.commissionReport else None
        currency = contract.currency

        row = {
            "ts_code": ts_code,
            "side": side,
            "price": price,
            "quantity": quantity,
            "position_before": None,
            "position_after": None,
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

        # 写入数据库
        conn.execute("""
            INSERT INTO trades(
                ts_code, side, price, quantity, position_before, position_after,
                reason, stop_loss, take_profit, note, timestamp,
                source, ibkr_exec_id, ibkr_order_id, commission, currency
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            row["ts_code"], row["side"], row["price"], row["quantity"],
            row["position_before"], row["position_after"], row["reason"],
            row["stop_loss"], row["take_profit"], row["note"], row["timestamp"],
            row["source"], row["ibkr_exec_id"], row["ibkr_order_id"],
            row["commission"], row["currency"]
        ))

        # 写入 Markdown
        md_path = os.path.join(md_base, f"{ts_code}.md")
        append_md(md_path, row)

        new_count += 1
        print(f"  同步: {ts_code} {side} {quantity} @ {price}")

    conn.commit()
    return new_count


def get_positions(ib: IB) -> list:
    """获取当前持仓"""
    positions = ib.positions()
    result = []
    for pos in positions:
        ts_code = convert_symbol(pos.contract)
        result.append({
            "ts_code": ts_code,
            "quantity": int(pos.position),
            "avg_cost": pos.avgCost,
            "market_value": pos.marketValue if hasattr(pos, 'marketValue') else None,
            "account": pos.account,
        })
    return result


def main():
    parser = argparse.ArgumentParser(description="IBKR 交易记录同步工具")
    parser.add_argument("--workspace", required=True, help="工作目录")
    parser.add_argument("--host", default="127.0.0.1", help="TWS/Gateway 主机 (默认: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=7497, help="TWS/Gateway 端口 (默认: 7497 Paper Trading)")
    parser.add_argument("--client-id", type=int, default=1, help="客户端 ID (默认: 1)")
    parser.add_argument("--days", type=int, default=7, help="同步最近 N 天的记录 (默认: 7)")
    parser.add_argument("--positions", action="store_true", help="显示当前持仓")
    parser.add_argument("--readonly", action="store_true", help="只读模式，只显示不写入")
    args = parser.parse_args()

    base = os.path.join(args.workspace, "results", "trade-journal")
    db_path = os.path.join(base, "db", "trades.db")
    md_base = os.path.join(base, "records")

    print(f"连接到 IBKR TWS/Gateway ({args.host}:{args.port})...")

    ib = IB()
    try:
        ib.connect(args.host, args.port, clientId=args.client_id, readonly=True)
        print(f"已连接! 账户: {ib.managedAccounts()}")

        if args.positions:
            print("\n=== 当前持仓 ===")
            positions = get_positions(ib)
            if positions:
                for pos in positions:
                    print(f"  {pos['ts_code']}: {pos['quantity']} 股 @ 均价 {pos['avg_cost']:.2f}")
            else:
                print("  无持仓")
            print()

        if not args.readonly:
            conn = ensure_db(db_path)
            print(f"\n=== 同步执行记录 (最近 {args.days} 天) ===")
            new_count = sync_executions(ib, conn, md_base, args.days)
            conn.close()
            print(f"\n同步完成! 新增 {new_count} 条交易记录")
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
