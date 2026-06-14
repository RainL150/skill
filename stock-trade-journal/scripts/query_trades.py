#!/usr/bin/env python3
import argparse
import os
import sqlite3


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--workspace",
        default=os.path.expanduser(os.environ.get("STJ_WORKSPACE", "~/.trade-journal")),
        help="工作目录 (默认: STJ_WORKSPACE 或 ~/.trade-journal)",
    )
    p.add_argument("--ts-code", required=True)
    p.add_argument("--limit", type=int, default=20)
    args = p.parse_args()

    db = os.path.join(args.workspace, "results", "trade-journal", "db", "trades.db")
    conn = sqlite3.connect(db)
    rows = conn.execute(
        """
        SELECT timestamp, ts_code, exchange, side, price, quantity, position_after, note
        FROM trades
        WHERE ts_code=?
        ORDER BY id DESC
        LIMIT ?
        """,
        (args.ts_code, args.limit)
    ).fetchall()
    conn.close()

    for r in rows:
        print(" | ".join("" if v is None else str(v) for v in r))


if __name__ == "__main__":
    main()
