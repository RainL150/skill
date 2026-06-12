#!/usr/bin/env python3
"""
数据库 Schema 定义和初始化

表结构：
1. trades - 交易记录表
2. positions - 持仓表（与交易联动）
3. watchlist - 关注列表
4. watch_notes - 关注记录/观察笔记
"""

import os
import sqlite3
from datetime import datetime
from typing import Any, Optional


def ensure_db(db_path: str) -> sqlite3.Connection:
    """确保数据库和所有表存在"""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # 支持字典式访问

    # 交易记录表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            exchange TEXT,                   -- 交易所 (NASDAQ/NYSE/HKEX/SSE/SZSE)
            side TEXT NOT NULL,              -- BUY/SELL
            price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            amount REAL,                     -- 交易金额 = price * quantity
            position_before INTEGER,         -- 交易前持仓
            position_after INTEGER,          -- 交易后持仓
            reason TEXT,
            stop_loss REAL,
            take_profit TEXT,
            note TEXT,
            timestamp TEXT NOT NULL,
            source TEXT DEFAULT 'manual',    -- manual/ibkr/import
            ibkr_exec_id TEXT,
            ibkr_order_id INTEGER,
            commission REAL,
            currency TEXT DEFAULT 'CNY',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 持仓表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL UNIQUE,    -- 股票代码（唯一）
            exchange TEXT,                   -- 交易所 (NASDAQ/NYSE/HKEX/SSE/SZSE)
            quantity INTEGER NOT NULL DEFAULT 0,  -- 当前持仓数量
            avg_cost REAL,                   -- 平均成本
            total_cost REAL,                 -- 总成本
            market_price REAL,               -- 最新市价
            market_value REAL,               -- 市值
            unrealized_pnl REAL,             -- 未实现盈亏
            realized_pnl REAL DEFAULT 0,     -- 已实现盈亏
            currency TEXT DEFAULT 'CNY',
            first_buy_date TEXT,             -- 首次买入日期
            last_trade_date TEXT,            -- 最后交易日期
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 持仓快照表（用于历史记录）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS position_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            ts_code TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            avg_cost REAL,
            market_price REAL,
            market_value REAL,
            unrealized_pnl REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 关注列表表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL UNIQUE,    -- 股票代码（唯一）
            exchange TEXT,                   -- 交易所
            name TEXT,                       -- 股票名称
            category TEXT DEFAULT 'default', -- 分类/标签
            target_price REAL,               -- 目标价
            stop_loss REAL,                  -- 止损价
            reason TEXT,                     -- 关注原因
            priority INTEGER DEFAULT 0,      -- 优先级 (0=普通, 1=重点, 2=紧急)
            status TEXT DEFAULT 'watching',  -- watching/bought/removed
            note TEXT,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 关注记录表：没有买卖行为，只记录观察笔记
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watch_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            exchange TEXT,
            note TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            source TEXT DEFAULT 'manual',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 创建索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_ts_code ON trades(ts_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_positions_ts_code ON positions(ts_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_date ON position_snapshots(snapshot_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_ts_code ON watchlist(ts_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_category ON watchlist(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_watch_notes_ts_code ON watch_notes(ts_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_watch_notes_timestamp ON watch_notes(timestamp)")

    conn.commit()

    # 迁移：为旧表添加新列
    _migrate_tables(conn)

    return conn


def _migrate_tables(conn: sqlite3.Connection) -> None:
    """迁移旧表结构"""
    # trades 表新增列
    trades_columns = [
        ("amount", "REAL"),
        ("created_at", "TEXT DEFAULT CURRENT_TIMESTAMP"),
        ("exchange", "TEXT"),
    ]
    for col_name, col_type in trades_columns:
        try:
            conn.execute(f"ALTER TABLE trades ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass  # 列已存在

    # positions 表新增列
    positions_columns = [
        ("exchange", "TEXT"),
    ]
    for col_name, col_type in positions_columns:
        try:
            conn.execute(f"ALTER TABLE positions ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass  # 列已存在

    conn.commit()


def parse_ts_code(ts_code: str) -> tuple[str, str, str]:
    """
    解析统一代码，返回 (symbol, market, exchange)

    Examples:
        AAPL.US -> ('AAPL', 'US', 'NASDAQ')  # 默认，实际可能是 NYSE
        0700.HK -> ('0700', 'HK', 'HKEX')
        600519.SH -> ('600519', 'SH', 'SSE')
        000001.SZ -> ('000001', 'SZ', 'SZSE')
    """
    parts = ts_code.rsplit('.', 1)
    if len(parts) != 2:
        return (ts_code, '', '')

    symbol, market = parts
    market = market.upper()

    market_exchange = {
        'US': 'NASDAQ',  # 默认，可通过 IBKR 更新为实际交易所
        'HK': 'HKEX',
        'SH': 'SSE',
        'SZ': 'SZSE',
    }

    return (symbol, market, market_exchange.get(market, market))


def update_position_after_trade(conn: sqlite3.Connection, trade: dict[str, Any]) -> None:
    """
    交易后更新持仓表

    Args:
        conn: 数据库连接
        trade: 交易记录字典，必须包含 ts_code, side, price, quantity
               可选: exchange, currency, timestamp
    """
    ts_code = trade["ts_code"]
    side = trade["side"].upper()
    price = trade["price"]
    quantity = trade["quantity"]
    timestamp = trade.get("timestamp", datetime.now().isoformat())
    currency = trade.get("currency", "CNY")
    fallback_exchange = parse_ts_code(ts_code)[2]
    exchange = trade.get("exchange") or fallback_exchange

    # 获取当前持仓
    cursor = conn.execute(
        "SELECT * FROM positions WHERE ts_code = ?", (ts_code,)
    )
    row = cursor.fetchone()

    if row is None:
        # 新建持仓
        if side == "BUY":
            conn.execute("""
                INSERT INTO positions (
                    ts_code, exchange, quantity, avg_cost, total_cost, currency,
                    first_buy_date, last_trade_date, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ts_code, exchange, quantity, price, price * quantity, currency,
                timestamp, timestamp, datetime.now().isoformat()
            ))
        else:
            # 卖出但没有持仓，记录负数（可能是做空或数据不一致）
            conn.execute("""
                INSERT INTO positions (
                    ts_code, exchange, quantity, avg_cost, total_cost, currency,
                    first_buy_date, last_trade_date, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ts_code, exchange, -quantity, price, 0, currency,
                timestamp, timestamp, datetime.now().isoformat()
            ))
    else:
        # 更新持仓
        current_qty = row["quantity"]
        current_avg_cost = row["avg_cost"] or 0
        current_total_cost = row["total_cost"] or 0
        realized_pnl = row["realized_pnl"] or 0
        # 更新交易所（IBKR 的 primaryExchange 比 .US 默认推断更准确）
        current_exchange = row["exchange"] if "exchange" in row.keys() else None
        if exchange and (
            not current_exchange
            or current_exchange == fallback_exchange
            or trade.get("source") == "ibkr"
        ):
            current_exchange = exchange

        if side == "BUY":
            # 买入：增加持仓，重新计算均价
            new_qty = current_qty + quantity
            new_total_cost = current_total_cost + (price * quantity)
            # 修复: 防止除零错误
            new_avg_cost = new_total_cost / new_qty if new_qty != 0 else 0
        else:
            # 卖出：减少持仓，计算已实现盈亏
            new_qty = current_qty - quantity
            # 已实现盈亏 = (卖出价 - 均价) * 卖出数量
            trade_pnl = (price - current_avg_cost) * quantity
            realized_pnl += trade_pnl

            if new_qty > 0:
                new_total_cost = current_avg_cost * new_qty
                new_avg_cost = current_avg_cost  # 均价不变
            else:
                new_total_cost = 0
                new_avg_cost = 0

        conn.execute("""
            UPDATE positions SET
                quantity = ?,
                avg_cost = ?,
                total_cost = ?,
                realized_pnl = ?,
                exchange = COALESCE(?, exchange),
                last_trade_date = ?,
                updated_at = ?
            WHERE ts_code = ?
        """, (
            new_qty, new_avg_cost, new_total_cost, realized_pnl,
            current_exchange, timestamp, datetime.now().isoformat(), ts_code
        ))

    conn.commit()


def sync_positions_from_ibkr(conn: sqlite3.Connection, ibkr_positions: list[dict[str, Any]]) -> None:
    """
    从 IBKR 同步持仓数据

    Args:
        conn: 数据库连接
        ibkr_positions: IBKR 持仓列表
    """
    now = datetime.now().isoformat()

    for pos in ibkr_positions:
        ts_code = pos["ts_code"]
        quantity = pos["quantity"]
        avg_cost = pos.get("avg_cost", 0)
        market_value = pos.get("market_value")
        currency = pos.get("currency", "USD")
        exchange = pos.get("exchange") or parse_ts_code(ts_code)[2]

        # 计算市价和未实现盈亏
        market_price = market_value / quantity if quantity and market_value else None
        unrealized_pnl = (market_price - avg_cost) * quantity if market_price and avg_cost else None

        conn.execute("""
            INSERT INTO positions (
                ts_code, exchange, quantity, avg_cost, total_cost, market_price,
                market_value, unrealized_pnl, currency, last_trade_date, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ts_code) DO UPDATE SET
                exchange = COALESCE(excluded.exchange, positions.exchange),
                quantity = excluded.quantity,
                avg_cost = excluded.avg_cost,
                total_cost = excluded.total_cost,
                market_price = excluded.market_price,
                market_value = excluded.market_value,
                unrealized_pnl = excluded.unrealized_pnl,
                currency = excluded.currency,
                updated_at = excluded.updated_at
        """, (
            ts_code, exchange, quantity, avg_cost, avg_cost * quantity if avg_cost else 0,
            market_price, market_value, unrealized_pnl, currency, now, now
        ))

    conn.commit()


def get_positions(conn: sqlite3.Connection, include_zero: bool = False) -> list[dict[str, Any]]:
    """获取所有持仓"""
    if include_zero:
        cursor = conn.execute("SELECT * FROM positions ORDER BY ts_code")
    else:
        cursor = conn.execute("SELECT * FROM positions WHERE quantity != 0 ORDER BY ts_code")
    return [dict(row) for row in cursor.fetchall()]


def get_position(conn: sqlite3.Connection, ts_code: str) -> Optional[dict[str, Any]]:
    """获取单个股票持仓"""
    cursor = conn.execute("SELECT * FROM positions WHERE ts_code = ?", (ts_code,))
    row = cursor.fetchone()
    return dict(row) if row else None


def take_position_snapshot(conn: sqlite3.Connection, snapshot_date: Optional[str] = None) -> int:
    """保存持仓快照"""
    if snapshot_date is None:
        snapshot_date = datetime.now().strftime("%Y-%m-%d")

    positions = get_positions(conn)
    for pos in positions:
        conn.execute("""
            INSERT INTO position_snapshots (
                snapshot_date, ts_code, quantity, avg_cost,
                market_price, market_value, unrealized_pnl
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            snapshot_date, pos["ts_code"], pos["quantity"], pos["avg_cost"],
            pos.get("market_price"), pos.get("market_value"), pos.get("unrealized_pnl")
        ))

    conn.commit()
    return len(positions)


if __name__ == "__main__":
    # 测试
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = ensure_db(db_path)
    print(f"数据库创建成功: {db_path}")

    # 模拟交易
    trade1 = {"ts_code": "AAPL.US", "side": "BUY", "price": 150.0, "quantity": 100}
    update_position_after_trade(conn, trade1)
    print(f"买入后持仓: {get_position(conn, 'AAPL.US')}")

    trade2 = {"ts_code": "AAPL.US", "side": "BUY", "price": 160.0, "quantity": 50}
    update_position_after_trade(conn, trade2)
    print(f"加仓后持仓: {get_position(conn, 'AAPL.US')}")

    trade3 = {"ts_code": "AAPL.US", "side": "SELL", "price": 170.0, "quantity": 80}
    update_position_after_trade(conn, trade3)
    print(f"卖出后持仓: {get_position(conn, 'AAPL.US')}")

    conn.close()
    os.unlink(db_path)
    print("测试完成")
