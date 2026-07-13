#!/usr/bin/env python3
"""
数据库 Schema 定义和初始化

表结构：
1. trades - 交易记录表
2. positions - 持仓表（与交易联动）
3. watchlist - 关注列表
4. notes - 统一标的笔记
5. watch_notes - 旧关注记录表（保留兼容，读取已迁移到 notes）
6. sectors / sector_* - 板块知识、产业链与关联标的
7. research_records - 用户确认保存的 AI 研究记录
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse


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
SECTOR_STATUSES = ("active", "archived")
SECTOR_STAGES = ("upstream", "midstream", "downstream")
KNOWLEDGE_KINDS = ("core", "driver", "risk", "evidence", "question")
RESEARCH_SCOPES = ("page", "portfolio", "symbol", "sector")


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


def _normalize_enum(value: str, choices: tuple[str, ...], label: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized not in choices:
        raise ValueError(f"invalid {label}: {value}. expected one of {', '.join(choices)}")
    return normalized


def normalize_sector_status(value: str) -> str:
    return _normalize_enum(value, SECTOR_STATUSES, "sector status")


def normalize_sector_stage(value: str) -> str:
    return _normalize_enum(value, SECTOR_STAGES, "sector stage")


def normalize_knowledge_kind(value: str) -> str:
    return _normalize_enum(value, KNOWLEDGE_KINDS, "knowledge kind")


def normalize_research_scope(value: str) -> str:
    return _normalize_enum(value, RESEARCH_SCOPES, "research scope")


def normalize_source_url(value: Any) -> str:
    clean = str(value or "").strip()
    if not clean:
        return ""
    if len(clean) > 2000:
        raise ValueError("source URL is too long")
    parsed = urlparse(clean)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("source URL must be an http(s) URL without credentials")
    return clean


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
    conn.execute("PRAGMA foreign_keys = ON")

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

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sectors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            summary TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sector_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sector_id INTEGER NOT NULL REFERENCES sectors(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(sector_id, name)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sector_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sector_id INTEGER NOT NULL REFERENCES sectors(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            stage TEXT NOT NULL CHECK (stage IN ('upstream', 'midstream', 'downstream')),
            description TEXT DEFAULT '',
            bottleneck INTEGER NOT NULL DEFAULT 0 CHECK (bottleneck IN (0, 1)),
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sector_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sector_id INTEGER NOT NULL REFERENCES sectors(id) ON DELETE CASCADE,
            from_node_id INTEGER NOT NULL REFERENCES sector_nodes(id) ON DELETE CASCADE,
            to_node_id INTEGER NOT NULL REFERENCES sector_nodes(id) ON DELETE CASCADE,
            relation TEXT NOT NULL DEFAULT 'supplies',
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(sector_id, from_node_id, to_node_id, relation)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sector_symbols (
            sector_id INTEGER NOT NULL REFERENCES sectors(id) ON DELETE CASCADE,
            ts_code TEXT NOT NULL,
            role TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(sector_id, ts_code)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sector_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sector_id INTEGER NOT NULL REFERENCES sectors(id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK (kind IN ('core', 'driver', 'risk', 'evidence', 'question')),
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            source_url TEXT DEFAULT '',
            as_of TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope_type TEXT NOT NULL CHECK (scope_type IN ('page', 'portfolio', 'symbol', 'sector')),
            ts_code TEXT,
            sector_id INTEGER REFERENCES sectors(id) ON DELETE SET NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            sources_json TEXT NOT NULL DEFAULT '[]',
            context_summary_json TEXT NOT NULL DEFAULT '{}',
            model_label TEXT DEFAULT '',
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sectors_status ON sectors(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sector_tags_sector ON sector_tags(sector_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sector_nodes_sector_stage ON sector_nodes(sector_id, stage)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sector_edges_sector ON sector_edges(sector_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sector_symbols_ts_code ON sector_symbols(ts_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sector_knowledge_sector_kind ON sector_knowledge(sector_id, kind)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_research_records_scope ON research_records(scope_type, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_research_records_ts_code ON research_records(ts_code)")


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


def get_watchlist(conn: sqlite3.Connection, include_removed: bool = False) -> list[dict[str, Any]]:
    """读取关注列表，默认排除已移除标的。"""
    where = "" if include_removed else "WHERE status != 'removed'"
    cursor = conn.execute(
        f"""
        SELECT *
        FROM watchlist
        {where}
        ORDER BY priority DESC, updated_at DESC, id DESC
        """
    )
    return [dict(row) for row in cursor.fetchall()]


def get_watch(conn: sqlite3.Connection, ts_code: str) -> Optional[dict[str, Any]]:
    row = conn.execute("SELECT * FROM watchlist WHERE ts_code = ?", (ts_code,)).fetchone()
    return dict(row) if row else None


def get_trades_for_symbol(conn: sqlite3.Connection, ts_code: str, limit: int = 100) -> list[dict[str, Any]]:
    cursor = conn.execute(
        """
        SELECT *
        FROM trades
        WHERE ts_code = ?
        ORDER BY timestamp DESC, id DESC
        LIMIT ?
        """,
        (ts_code, max(1, min(int(limit), 1000))),
    )
    return [dict(row) for row in cursor.fetchall()]


def _require_sector(conn: sqlite3.Connection, sector_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM sectors WHERE id = ?", (int(sector_id),)).fetchone()
    if not row:
        raise ValueError(f"sector not found: {sector_id}")
    return dict(row)


def create_sector(conn: sqlite3.Connection, name: str, summary: str = "", slug: str | None = None) -> dict[str, Any]:
    clean_name = (name or "").strip()
    if not clean_name or len(clean_name) > 80:
        raise ValueError("sector name must be 1-80 characters")
    clean_summary = (summary or "").strip()[:4000]
    clean_slug = (slug or f"sector-{uuid.uuid4().hex[:10]}").strip().lower()
    if not clean_slug or len(clean_slug) > 80 or not all(ch.isalnum() or ch in "-_" for ch in clean_slug):
        raise ValueError("invalid sector slug")
    now = datetime.now().isoformat()
    cursor = conn.execute(
        "INSERT INTO sectors (slug, name, summary, status, created_at, updated_at) VALUES (?, ?, ?, 'active', ?, ?)",
        (clean_slug, clean_name, clean_summary, now, now),
    )
    conn.commit()
    return get_sector(conn, int(cursor.lastrowid))


def get_sector(conn: sqlite3.Connection, sector_id: int) -> dict[str, Any]:
    sector = _require_sector(conn, sector_id)
    sector["tags"] = [dict(row) for row in conn.execute(
        "SELECT * FROM sector_tags WHERE sector_id = ? ORDER BY name", (sector_id,)
    )]
    sector["nodes"] = [dict(row) for row in conn.execute(
        "SELECT * FROM sector_nodes WHERE sector_id = ? ORDER BY sort_order, id", (sector_id,)
    )]
    sector["edges"] = [dict(row) for row in conn.execute(
        "SELECT * FROM sector_edges WHERE sector_id = ? ORDER BY sort_order, id", (sector_id,)
    )]
    sector["symbols"] = [dict(row) for row in conn.execute(
        "SELECT * FROM sector_symbols WHERE sector_id = ? ORDER BY ts_code", (sector_id,)
    )]
    sector["knowledge"] = [dict(row) for row in conn.execute(
        "SELECT * FROM sector_knowledge WHERE sector_id = ? ORDER BY kind, updated_at DESC, id DESC", (sector_id,)
    )]
    return sector


def list_sectors(conn: sqlite3.Connection, include_archived: bool = False) -> list[dict[str, Any]]:
    where = "" if include_archived else "WHERE status = 'active'"
    ids = [row["id"] for row in conn.execute(
        f"SELECT id FROM sectors {where} ORDER BY updated_at DESC, id DESC"
    )]
    return [get_sector(conn, int(sector_id)) for sector_id in ids]


def update_sector(conn: sqlite3.Connection, sector_id: int, **changes: Any) -> dict[str, Any]:
    _require_sector(conn, sector_id)
    allowed: dict[str, Any] = {}
    if "name" in changes:
        name = str(changes["name"] or "").strip()
        if not name or len(name) > 80:
            raise ValueError("sector name must be 1-80 characters")
        allowed["name"] = name
    if "summary" in changes:
        allowed["summary"] = str(changes["summary"] or "").strip()[:4000]
    if "status" in changes:
        allowed["status"] = normalize_sector_status(str(changes["status"]))
    if not allowed:
        return get_sector(conn, sector_id)
    allowed["updated_at"] = datetime.now().isoformat()
    assignments = ", ".join(f"{column} = ?" for column in allowed)
    conn.execute(
        f"UPDATE sectors SET {assignments} WHERE id = ?",
        (*allowed.values(), int(sector_id)),
    )
    conn.commit()
    return get_sector(conn, sector_id)


def archive_sector(conn: sqlite3.Connection, sector_id: int) -> dict[str, Any]:
    return update_sector(conn, sector_id, status="archived")


def add_sector_tag(conn: sqlite3.Connection, sector_id: int, name: str) -> dict[str, Any]:
    _require_sector(conn, sector_id)
    clean = (name or "").strip()
    if not clean or len(clean) > 40:
        raise ValueError("tag must be 1-40 characters")
    conn.execute(
        "INSERT OR IGNORE INTO sector_tags (sector_id, name, created_at) VALUES (?, ?, ?)",
        (sector_id, clean, datetime.now().isoformat()),
    )
    conn.execute("UPDATE sectors SET updated_at = ? WHERE id = ?", (datetime.now().isoformat(), sector_id))
    conn.commit()
    row = conn.execute("SELECT * FROM sector_tags WHERE sector_id = ? AND name = ?", (sector_id, clean)).fetchone()
    return dict(row)


def delete_sector_tag(conn: sqlite3.Connection, sector_id: int, tag_id: int) -> bool:
    cursor = conn.execute("DELETE FROM sector_tags WHERE id = ? AND sector_id = ?", (tag_id, sector_id))
    conn.commit()
    return cursor.rowcount > 0


def add_sector_node(
    conn: sqlite3.Connection,
    sector_id: int,
    name: str,
    stage: str,
    description: str = "",
    bottleneck: bool = False,
    sort_order: int = 0,
) -> dict[str, Any]:
    _require_sector(conn, sector_id)
    clean_name = (name or "").strip()
    if not clean_name or len(clean_name) > 100:
        raise ValueError("node name must be 1-100 characters")
    cursor = conn.execute(
        """
        INSERT INTO sector_nodes (
            sector_id, name, stage, description, bottleneck, sort_order, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sector_id,
            clean_name,
            normalize_sector_stage(stage),
            (description or "").strip()[:4000],
            1 if bottleneck else 0,
            int(sort_order),
            datetime.now().isoformat(),
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM sector_nodes WHERE id = ?", (cursor.lastrowid,)).fetchone())


def update_sector_node(conn: sqlite3.Connection, sector_id: int, node_id: int, **changes: Any) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM sector_nodes WHERE id = ? AND sector_id = ?", (node_id, sector_id)).fetchone()
    if not row:
        raise ValueError(f"sector node not found: {node_id}")
    values = dict(row)
    if "name" in changes:
        name = str(changes["name"] or "").strip()
        if not name or len(name) > 100:
            raise ValueError("node name must be 1-100 characters")
        values["name"] = name
    if "stage" in changes:
        values["stage"] = normalize_sector_stage(str(changes["stage"]))
    if "description" in changes:
        values["description"] = str(changes["description"] or "").strip()[:4000]
    if "bottleneck" in changes:
        values["bottleneck"] = 1 if changes["bottleneck"] else 0
    if "sort_order" in changes:
        values["sort_order"] = int(changes["sort_order"])
    conn.execute(
        """
        UPDATE sector_nodes
        SET name = ?, stage = ?, description = ?, bottleneck = ?, sort_order = ?, updated_at = ?
        WHERE id = ? AND sector_id = ?
        """,
        (
            values["name"], values["stage"], values["description"], values["bottleneck"],
            values["sort_order"], datetime.now().isoformat(), node_id, sector_id,
        ),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM sector_nodes WHERE id = ?", (node_id,)).fetchone())


def delete_sector_node(conn: sqlite3.Connection, sector_id: int, node_id: int) -> bool:
    with conn:
        conn.execute(
            "DELETE FROM sector_edges WHERE sector_id = ? AND (from_node_id = ? OR to_node_id = ?)",
            (sector_id, node_id, node_id),
        )
        cursor = conn.execute("DELETE FROM sector_nodes WHERE id = ? AND sector_id = ?", (node_id, sector_id))
    return cursor.rowcount > 0


def add_sector_edge(
    conn: sqlite3.Connection,
    sector_id: int,
    from_node_id: int,
    to_node_id: int,
    relation: str = "supplies",
    sort_order: int = 0,
) -> dict[str, Any]:
    _require_sector(conn, sector_id)
    if from_node_id == to_node_id:
        raise ValueError("sector edge cannot point to itself")
    node_count = conn.execute(
        "SELECT COUNT(*) AS n FROM sector_nodes WHERE sector_id = ? AND id IN (?, ?)",
        (sector_id, from_node_id, to_node_id),
    ).fetchone()["n"]
    if node_count != 2:
        raise ValueError("edge nodes must belong to the sector")
    clean_relation = (relation or "supplies").strip()[:80]
    cursor = conn.execute(
        """
        INSERT INTO sector_edges (sector_id, from_node_id, to_node_id, relation, sort_order, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (sector_id, from_node_id, to_node_id, clean_relation, int(sort_order), datetime.now().isoformat()),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM sector_edges WHERE id = ?", (cursor.lastrowid,)).fetchone())


def delete_sector_edge(conn: sqlite3.Connection, sector_id: int, edge_id: int) -> bool:
    cursor = conn.execute("DELETE FROM sector_edges WHERE id = ? AND sector_id = ?", (edge_id, sector_id))
    conn.commit()
    return cursor.rowcount > 0


def add_sector_symbol(conn: sqlite3.Connection, sector_id: int, ts_code: str, role: str = "", note: str = "") -> dict[str, Any]:
    _require_sector(conn, sector_id)
    parse_ts_code(ts_code)
    conn.execute(
        """
        INSERT INTO sector_symbols (sector_id, ts_code, role, note, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(sector_id, ts_code) DO UPDATE SET role = excluded.role, note = excluded.note
        """,
        (sector_id, ts_code.upper(), (role or "").strip()[:100], (note or "").strip()[:2000], datetime.now().isoformat()),
    )
    conn.commit()
    return dict(conn.execute(
        "SELECT * FROM sector_symbols WHERE sector_id = ? AND ts_code = ?", (sector_id, ts_code.upper())
    ).fetchone())


def delete_sector_symbol(conn: sqlite3.Connection, sector_id: int, ts_code: str) -> bool:
    cursor = conn.execute("DELETE FROM sector_symbols WHERE sector_id = ? AND ts_code = ?", (sector_id, ts_code.upper()))
    conn.commit()
    return cursor.rowcount > 0


def add_sector_knowledge(
    conn: sqlite3.Connection,
    sector_id: int,
    kind: str,
    title: str,
    content: str,
    source_url: str = "",
    as_of: str | None = None,
) -> dict[str, Any]:
    _require_sector(conn, sector_id)
    clean_title = (title or "").strip()
    clean_content = (content or "").strip()
    if not clean_title or len(clean_title) > 200:
        raise ValueError("knowledge title must be 1-200 characters")
    if not clean_content or len(clean_content) > 20_000:
        raise ValueError("knowledge content must be 1-20000 characters")
    now = datetime.now().isoformat()
    cursor = conn.execute(
        """
        INSERT INTO sector_knowledge (
            sector_id, kind, title, content, source_url, as_of, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sector_id, normalize_knowledge_kind(kind), clean_title, clean_content,
            normalize_source_url(source_url), as_of, now, now,
        ),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM sector_knowledge WHERE id = ?", (cursor.lastrowid,)).fetchone())


def update_sector_knowledge(conn: sqlite3.Connection, sector_id: int, knowledge_id: int, **changes: Any) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM sector_knowledge WHERE id = ? AND sector_id = ?", (knowledge_id, sector_id)
    ).fetchone()
    if not row:
        raise ValueError(f"sector knowledge not found: {knowledge_id}")
    values = dict(row)
    if "kind" in changes:
        values["kind"] = normalize_knowledge_kind(str(changes["kind"]))
    if "title" in changes:
        values["title"] = str(changes["title"] or "").strip()[:200]
    if "content" in changes:
        values["content"] = str(changes["content"] or "").strip()[:20_000]
    if not values["title"] or not values["content"]:
        raise ValueError("knowledge title and content are required")
    if "source_url" in changes:
        values["source_url"] = normalize_source_url(changes["source_url"])
    if "as_of" in changes:
        values["as_of"] = changes["as_of"]
    conn.execute(
        """
        UPDATE sector_knowledge
        SET kind = ?, title = ?, content = ?, source_url = ?, as_of = ?, updated_at = ?
        WHERE id = ? AND sector_id = ?
        """,
        (
            values["kind"], values["title"], values["content"], values["source_url"],
            values["as_of"], datetime.now().isoformat(), knowledge_id, sector_id,
        ),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM sector_knowledge WHERE id = ?", (knowledge_id,)).fetchone())


def delete_sector_knowledge(conn: sqlite3.Connection, sector_id: int, knowledge_id: int) -> bool:
    cursor = conn.execute(
        "DELETE FROM sector_knowledge WHERE id = ? AND sector_id = ?", (knowledge_id, sector_id)
    )
    conn.commit()
    return cursor.rowcount > 0


def add_research_record(
    conn: sqlite3.Connection,
    *,
    scope_type: str,
    question: str,
    answer: str,
    ts_code: str | None = None,
    sector_id: int | None = None,
    sources: list[dict[str, Any]] | None = None,
    context_summary: dict[str, Any] | None = None,
    model_label: str = "",
) -> dict[str, Any]:
    scope = normalize_research_scope(scope_type)
    clean_question = (question or "").strip()
    clean_answer = (answer or "").strip()
    if not clean_question or not clean_answer:
        raise ValueError("question and answer are required")
    if ts_code:
        parse_ts_code(ts_code)
        ts_code = ts_code.upper()
    if sector_id is not None:
        _require_sector(conn, sector_id)
    cursor = conn.execute(
        """
        INSERT INTO research_records (
            scope_type, ts_code, sector_id, question, answer, sources_json,
            context_summary_json, model_label, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scope, ts_code, sector_id, clean_question[:20_000], clean_answer[:100_000],
            json.dumps(sources or [], ensure_ascii=False),
            json.dumps(context_summary or {}, ensure_ascii=False),
            (model_label or "").strip()[:200], datetime.now().isoformat(),
        ),
    )
    conn.commit()
    return get_research_record(conn, int(cursor.lastrowid))


def get_research_record(conn: sqlite3.Connection, record_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM research_records WHERE id = ?", (record_id,)).fetchone()
    if not row:
        raise ValueError(f"research record not found: {record_id}")
    item = dict(row)
    for source, target in (("sources_json", "sources"), ("context_summary_json", "context_summary")):
        try:
            item[target] = json.loads(item.pop(source))
        except (TypeError, json.JSONDecodeError):
            item[target] = [] if target == "sources" else {}
    return item


def list_research_records(
    conn: sqlite3.Connection,
    *,
    scope_type: str | None = None,
    ts_code: str | None = None,
    sector_id: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    filters: list[str] = []
    params: list[Any] = []
    if scope_type:
        filters.append("scope_type = ?")
        params.append(normalize_research_scope(scope_type))
    if ts_code:
        filters.append("ts_code = ?")
        params.append(ts_code.upper())
    if sector_id is not None:
        filters.append("sector_id = ?")
        params.append(int(sector_id))
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.append(max(1, min(int(limit), 200)))
    ids = [row["id"] for row in conn.execute(
        f"SELECT id FROM research_records {where} ORDER BY created_at DESC, id DESC LIMIT ?", params
    )]
    return [get_research_record(conn, int(record_id)) for record_id in ids]


def delete_research_record(conn: sqlite3.Connection, record_id: int) -> bool:
    """删除单条用户保存的 AI 研究记录。"""
    cursor = conn.execute("DELETE FROM research_records WHERE id = ?", (int(record_id),))
    conn.commit()
    return cursor.rowcount > 0


def clear_research_records(conn: sqlite3.Connection) -> int:
    """清空用户保存的 AI 研究记录并返回删除数量。"""
    cursor = conn.execute("DELETE FROM research_records")
    conn.commit()
    return max(0, int(cursor.rowcount))


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
