#!/usr/bin/env python3
"""
数据库 Schema 定义和初始化

表结构：
1. trades - 交易记录表
2. positions - 持仓表（与交易联动）
3. watchlist - 关注列表
4. notes - 统一标的笔记
5. watch_notes - 旧关注记录表（保留兼容，读取已迁移到 notes）
"""

import os
import sqlite3
from datetime import datetime
from typing import Any, Optional


IMPORT_NOTE_MARKERS = (
    "IBKR PDF import",
    "IBKR Order #",
    "东方财富截图导入",
    "截图导入",
    "source_images=",
    "source_pdf=",
    "account=",
    "settlement=",
    "raw_code=",
    "listing_exchange=",
)

NOTE_TYPES = ("trade_decision", "watch_observation", "holding_review")


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def normalize_note_type(note_type: str) -> str:
    """校验并规整统一笔记类型。"""
    value = (note_type or "").strip()
    if value not in NOTE_TYPES:
        raise ValueError(f"invalid note_type: {note_type}. expected one of {', '.join(NOTE_TYPES)}")
    return value


def _clean_note(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if any(marker in text for marker in IMPORT_NOTE_MARKERS):
        return ""
    return text


def _merge_notes(*values: Any) -> str:
    parts = [_clean_note(value) for value in values]
    return "；".join(dict.fromkeys(part for part in parts if part))


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
            priority INTEGER DEFAULT 0,      -- 优先级 (0=普通, 1=重点, 2=紧急)
            status TEXT DEFAULT 'watching',  -- watching/bought/removed
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

    # 统一标的笔记表：所有非组合笔记按 note_type 区分。
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            exchange TEXT,
            note_type TEXT NOT NULL CHECK (
                note_type IN ('trade_decision', 'watch_observation', 'holding_review')
            ),
            note TEXT NOT NULL,
            related_trade_id INTEGER,
            timestamp TEXT NOT NULL,
            source TEXT DEFAULT 'manual',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    # 迁移：为旧表添加新列/移除旧列
    _migrate_tables(conn)

    # 表重建迁移会丢失旧索引，迁移后统一补齐。
    _create_indexes(conn)
    conn.commit()

    return conn


def _create_indexes(conn: sqlite3.Connection) -> None:
    """创建常用查询索引。"""
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_ts_code ON trades(ts_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_positions_ts_code ON positions(ts_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_date ON position_snapshots(snapshot_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_ts_code ON watchlist(ts_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_category ON watchlist(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_watch_notes_ts_code ON watch_notes(ts_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_watch_notes_timestamp ON watch_notes(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notes_ts_code ON notes(ts_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notes_note_type ON notes(note_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notes_timestamp ON notes(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notes_related_trade_id ON notes(related_trade_id)")


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

    _migrate_trades_note_only(conn)
    _migrate_watchlist_note_timeline(conn)
    _migrate_notes_table(conn)

    conn.commit()


def _migrate_trades_note_only(conn: sqlite3.Connection) -> None:
    """删除 trades.reason，旧 reason 与 note 合并为 note。"""
    columns = _table_columns(conn, "trades")
    if "reason" not in columns:
        return

    rows = [dict(row) for row in conn.execute("SELECT * FROM trades ORDER BY id")]
    conn.execute("ALTER TABLE trades RENAME TO trades_legacy")
    conn.execute("""
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            exchange TEXT,
            side TEXT NOT NULL,
            price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            amount REAL,
            position_before INTEGER,
            position_after INTEGER,
            stop_loss REAL,
            take_profit TEXT,
            note TEXT,
            timestamp TEXT NOT NULL,
            source TEXT DEFAULT 'manual',
            ibkr_exec_id TEXT,
            ibkr_order_id INTEGER,
            commission REAL,
            currency TEXT DEFAULT 'CNY',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for row in rows:
        note = _merge_notes(row.get("reason"), row.get("note"))
        conn.execute(
            """
            INSERT INTO trades (
                id, ts_code, exchange, side, price, quantity, amount,
                position_before, position_after, stop_loss, take_profit, note,
                timestamp, source, ibkr_exec_id, ibkr_order_id, commission,
                currency, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("id"),
                row.get("ts_code"),
                row.get("exchange"),
                row.get("side"),
                row.get("price"),
                row.get("quantity"),
                row.get("amount"),
                row.get("position_before"),
                row.get("position_after"),
                row.get("stop_loss"),
                row.get("take_profit"),
                note,
                row.get("timestamp"),
                row.get("source") or "manual",
                row.get("ibkr_exec_id"),
                row.get("ibkr_order_id"),
                row.get("commission"),
                row.get("currency") or "CNY",
                row.get("created_at"),
            ),
        )
    conn.execute("DROP TABLE trades_legacy")


def _migrate_watchlist_note_timeline(conn: sqlite3.Connection) -> None:
    """删除 watchlist.reason/note，旧文本迁入 watch_notes 时间线。"""
    columns = _table_columns(conn, "watchlist")
    if "reason" not in columns and "note" not in columns:
        return

    rows = [dict(row) for row in conn.execute("SELECT * FROM watchlist ORDER BY id")]
    for row in rows:
        note = _merge_notes(row.get("reason"), row.get("note"))
        if note:
            timestamp = row.get("updated_at") or row.get("added_at") or datetime.now().isoformat()
            exists = conn.execute(
                """
                SELECT 1 FROM watch_notes
                WHERE ts_code = ? AND note = ? AND source = 'watchlist_migration'
                LIMIT 1
                """,
                (row.get("ts_code"), note),
            ).fetchone()
            if not exists:
                conn.execute(
                    """
                    INSERT INTO watch_notes (ts_code, exchange, note, timestamp, source, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row.get("ts_code"),
                        row.get("exchange"),
                        note,
                        timestamp,
                        "watchlist_migration",
                        datetime.now().isoformat(),
                    ),
                )

    conn.execute("ALTER TABLE watchlist RENAME TO watchlist_legacy")
    conn.execute("""
        CREATE TABLE watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL UNIQUE,
            exchange TEXT,
            name TEXT,
            category TEXT DEFAULT 'default',
            target_price REAL,
            stop_loss REAL,
            priority INTEGER DEFAULT 0,
            status TEXT DEFAULT 'watching',
            added_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for row in rows:
        conn.execute(
            """
            INSERT INTO watchlist (
                id, ts_code, exchange, name, category, target_price, stop_loss,
                priority, status, added_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("id"),
                row.get("ts_code"),
                row.get("exchange"),
                row.get("name"),
                row.get("category") or "default",
                row.get("target_price"),
                row.get("stop_loss"),
                row.get("priority") or 0,
                row.get("status") or "watching",
                row.get("added_at"),
                row.get("updated_at"),
            ),
        )
    conn.execute("DROP TABLE watchlist_legacy")


def _watch_note_type_from_source(source: Any) -> str:
    """把旧 watch_notes 记录映射到统一笔记类型。"""
    value = str(source or "").strip().lower()
    if value == "holding_review" or value.startswith("holding_review"):
        return "holding_review"
    return "watch_observation"


def _resolve_note_exchange(conn: sqlite3.Connection, ts_code: str, exchange: Any = None) -> str:
    """笔记交易所优先继承本地持仓/关注中的真实交易所。"""
    fallback = parse_ts_code(ts_code)[2]
    current = str(exchange or "").strip()

    pos = conn.execute(
        "SELECT exchange FROM positions WHERE ts_code = ? AND exchange IS NOT NULL AND exchange != ''",
        (ts_code,),
    ).fetchone()
    if pos and (not current or current == fallback):
        return pos["exchange"]

    watch = conn.execute(
        "SELECT exchange FROM watchlist WHERE ts_code = ? AND exchange IS NOT NULL AND exchange != ''",
        (ts_code,),
    ).fetchone()
    if watch and (not current or current == fallback):
        return watch["exchange"]

    return current or fallback


def _note_exists(
    conn: sqlite3.Connection,
    ts_code: str,
    note_type: str,
    note: str,
    timestamp: str,
    related_trade_id: Any = None,
) -> bool:
    if related_trade_id is not None:
        row = conn.execute(
            """
            SELECT 1 FROM notes
            WHERE note_type = ? AND related_trade_id = ?
            LIMIT 1
            """,
            (note_type, related_trade_id),
        ).fetchone()
        if row:
            return True

    row = conn.execute(
        """
        SELECT 1 FROM notes
        WHERE ts_code = ? AND note_type = ? AND note = ? AND timestamp = ?
        LIMIT 1
        """,
        (ts_code, note_type, note, timestamp),
    ).fetchone()
    return row is not None


def _migrate_notes_table(conn: sqlite3.Connection) -> None:
    """把交易笔记和旧关注笔记迁入统一 notes 表。"""
    trade_rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, ts_code, exchange, note, timestamp, source, created_at
            FROM trades
            WHERE note IS NOT NULL AND TRIM(note) != ''
            ORDER BY id
            """
        )
    ]
    for row in trade_rows:
        note = _clean_note(row.get("note"))
        if not note:
            continue
        timestamp = row.get("timestamp") or datetime.now().isoformat()
        if _note_exists(conn, row["ts_code"], "trade_decision", note, timestamp, row.get("id")):
            continue
        conn.execute(
            """
            INSERT INTO notes (
                ts_code, exchange, note_type, note, related_trade_id,
                timestamp, source, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["ts_code"],
                _resolve_note_exchange(conn, row["ts_code"], row.get("exchange")),
                "trade_decision",
                note,
                row.get("id"),
                timestamp,
                row.get("source") or "trade_migration",
                row.get("created_at") or datetime.now().isoformat(),
            ),
        )

    _migrate_legacy_watch_notes(conn)
    _refresh_note_exchanges(conn)


def _migrate_legacy_watch_notes(conn: sqlite3.Connection) -> None:
    """把旧 watch_notes 迁入统一 notes 表。"""
    if not _table_exists(conn, "watch_notes"):
        return

    watch_rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, ts_code, exchange, note, timestamp, source, created_at
            FROM watch_notes
            WHERE note IS NOT NULL AND TRIM(note) != ''
            ORDER BY id
            """
        )
    ]
    for row in watch_rows:
        note = _clean_note(row.get("note"))
        if not note:
            continue
        note_type = _watch_note_type_from_source(row.get("source"))
        timestamp = row.get("timestamp") or datetime.now().isoformat()
        if _note_exists(conn, row["ts_code"], note_type, note, timestamp):
            continue
        conn.execute(
            """
            INSERT INTO notes (
                ts_code, exchange, note_type, note, related_trade_id,
                timestamp, source, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["ts_code"],
                _resolve_note_exchange(conn, row["ts_code"], row.get("exchange")),
                note_type,
                note,
                None,
                timestamp,
                row.get("source") or "watch_notes_migration",
                row.get("created_at") or datetime.now().isoformat(),
            ),
        )


def _refresh_note_exchanges(conn: sqlite3.Connection) -> None:
    """用持仓/关注里的真实交易所修正 notes 中的默认推断值。"""
    rows = [
        dict(row)
        for row in conn.execute(
            "SELECT id, ts_code, exchange FROM notes ORDER BY id"
        )
    ]
    for row in rows:
        resolved = _resolve_note_exchange(conn, row["ts_code"], row.get("exchange"))
        if resolved and resolved != row.get("exchange"):
            conn.execute(
                "UPDATE notes SET exchange = ? WHERE id = ?",
                (resolved, row["id"]),
            )


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


def add_note(
    conn: sqlite3.Connection,
    ts_code: str,
    note: str,
    note_type: str,
    timestamp: Optional[str] = None,
    source: str = "manual",
    exchange: Optional[str] = None,
    related_trade_id: Optional[int] = None,
) -> dict[str, Any]:
    """写入统一标的笔记。"""
    clean_note = _clean_note(note)
    if not clean_note:
        return {"success": False, "ts_code": ts_code, "message": "笔记不能为空"}

    normalized_type = normalize_note_type(note_type)
    ts = timestamp or datetime.now().isoformat()
    used_exchange = _resolve_note_exchange(conn, ts_code, exchange)
    cursor = conn.execute(
        """
        INSERT INTO notes (
            ts_code, exchange, note_type, note, related_trade_id,
            timestamp, source, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ts_code,
            used_exchange,
            normalized_type,
            clean_note,
            related_trade_id,
            ts,
            source,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    return {
        "success": True,
        "id": cursor.lastrowid,
        "ts_code": ts_code,
        "note_type": normalized_type,
        "message": "已添加笔记",
    }


def get_notes(
    conn: sqlite3.Connection,
    ts_code: str,
    note_type: Optional[str] = None,
    limit: int = 20,
    include_trade_decision: bool = True,
) -> list[dict[str, Any]]:
    """读取统一标的笔记。"""
    params: list[Any] = [ts_code]
    filters = ["ts_code = ?"]

    if note_type:
        filters.append("note_type = ?")
        params.append(normalize_note_type(note_type))
    elif not include_trade_decision:
        filters.append("note_type != 'trade_decision'")

    params.append(limit)
    cursor = conn.execute(
        f"""
        SELECT *
        FROM notes
        WHERE {' AND '.join(filters)}
        ORDER BY timestamp DESC, id DESC
        LIMIT ?
        """,
        params,
    )
    return [dict(row) for row in cursor.fetchall()]


def get_notes_map(
    conn: sqlite3.Connection,
    ts_codes: list[str],
    note_type: Optional[str] = None,
    limit: int = 10,
    include_trade_decision: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    """批量读取统一标的笔记，按代码分组。"""
    return {
        ts_code: get_notes(
            conn,
            ts_code,
            note_type=note_type,
            limit=limit,
            include_trade_decision=include_trade_decision,
        )
        for ts_code in ts_codes
    }


def get_trade_decision_note(conn: sqlite3.Connection, trade_id: int) -> str:
    """读取指定交易关联的交易决策笔记。"""
    row = conn.execute(
        """
        SELECT note
        FROM notes
        WHERE note_type = 'trade_decision' AND related_trade_id = ?
        ORDER BY timestamp DESC, id DESC
        LIMIT 1
        """,
        (trade_id,),
    ).fetchone()
    return row["note"] if row else ""


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
