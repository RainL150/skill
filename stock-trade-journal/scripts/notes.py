#!/usr/bin/env python3
"""统一标的笔记管理。"""

import argparse
import json
import os

from db_schema import NOTE_TYPES, add_note, ensure_db, get_notes, parse_ts_code


def print_notes(notes: list[dict]) -> None:
    if not notes:
        print("暂无笔记")
        return
    print(f"\n{'=' * 96}")
    print(f"  {'时间':<19} {'类型':<18} {'笔记'}")
    print(f"{'=' * 96}")
    for item in notes:
        print(
            f"  {(item.get('timestamp') or '')[:19]:<19} "
            f"{(item.get('note_type') or '-'):<18} {item.get('note') or '-'}"
        )
    print(f"{'=' * 96}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="统一标的笔记管理")
    parser.add_argument(
        "--workspace",
        default=os.path.expanduser(os.environ.get("STJ_WORKSPACE", "~/.trade-journal")),
        help="工作目录 (默认: STJ_WORKSPACE 或 ~/.trade-journal)",
    )

    subparsers = parser.add_subparsers(dest="command", help="命令")

    add_parser = subparsers.add_parser("add", help="添加标的笔记")
    add_parser.add_argument("ts_code", help="股票代码")
    add_parser.add_argument("--type", dest="note_type", required=True, choices=NOTE_TYPES, help="笔记类型")
    add_parser.add_argument("--note", "-n", required=True, help="笔记内容")
    add_parser.add_argument("--timestamp", help="记录时间，默认当前时间")
    add_parser.add_argument("--source", default="manual", help="来源")

    list_parser = subparsers.add_parser("list", aliases=["ls"], help="查看标的笔记")
    list_parser.add_argument("ts_code", help="股票代码")
    list_parser.add_argument("--type", dest="note_type", choices=NOTE_TYPES, help="只显示指定类型")
    list_parser.add_argument("--limit", type=int, default=20, help="最多显示 N 条")
    list_parser.add_argument("--json", action="store_true", help="JSON 格式输出")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    base = os.path.join(args.workspace, "results", "trade-journal")
    db_path = os.path.join(base, "db", "trades.db")
    conn = ensure_db(db_path)

    if args.command == "add":
        _, _, exchange = parse_ts_code(args.ts_code)
        result = add_note(
            conn,
            args.ts_code,
            args.note,
            note_type=args.note_type,
            timestamp=args.timestamp,
            source=args.source,
            exchange=exchange,
        )
        icon = "✅" if result["success"] else "⚠️"
        print(f"{icon} {result['message']}: {result['ts_code']} [{result.get('note_type', '-')}]")

    elif args.command in ("list", "ls"):
        notes = get_notes(conn, args.ts_code, note_type=args.note_type, limit=args.limit)
        if args.json:
            print(json.dumps(notes, indent=2, ensure_ascii=False))
        else:
            print_notes(notes)

    conn.close()


if __name__ == "__main__":
    main()
