#!/usr/bin/env python3
"""
关注列表管理工具 - 支持增删查改

功能:
1. 添加关注股票
2. 查看关注列表
3. 更新关注信息
4. 删除关注
5. 按分类筛选
"""

import argparse
import json
import os
from datetime import datetime
from typing import Any, Optional

from db_schema import NOTE_TYPES, add_note, ensure_db, get_notes, get_notes_map, parse_ts_code


def add_watch(
    conn,
    ts_code: str,
    name: str = "",
    category: str = "default",
    target_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    priority: int = 0,
) -> dict[str, Any]:
    """添加关注股票"""
    _, _, exchange = parse_ts_code(ts_code)

    try:
        conn.execute(
            """
            INSERT INTO watchlist (
                ts_code, exchange, name, category, target_price, stop_loss,
                priority, added_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                ts_code,
                exchange,
                name,
                category,
                target_price,
                stop_loss,
                priority,
                datetime.now().isoformat(),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        return {"success": True, "ts_code": ts_code, "message": "已添加到关注列表"}
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            return {"success": False, "ts_code": ts_code, "message": "已在关注列表中"}
        raise


def remove_watch(conn, ts_code: str) -> dict[str, Any]:
    """删除关注股票"""
    cursor = conn.execute("DELETE FROM watchlist WHERE ts_code = ?", (ts_code,))
    conn.commit()
    if cursor.rowcount > 0:
        return {"success": True, "ts_code": ts_code, "message": "已从关注列表移除"}
    return {"success": False, "ts_code": ts_code, "message": "未找到该股票"}


def update_watch(conn, ts_code: str, **kwargs) -> dict[str, Any]:
    """更新关注信息"""
    # 过滤有效字段
    valid_fields = [
        "name",
        "category",
        "target_price",
        "stop_loss",
        "priority",
        "status",
    ]
    updates = {k: v for k, v in kwargs.items() if k in valid_fields and v is not None}

    if not updates:
        return {"success": False, "ts_code": ts_code, "message": "无更新内容"}

    updates["updated_at"] = datetime.now().isoformat()

    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [ts_code]

    cursor = conn.execute(
        f"UPDATE watchlist SET {set_clause} WHERE ts_code = ?", values
    )
    conn.commit()

    if cursor.rowcount > 0:
        return {"success": True, "ts_code": ts_code, "message": "已更新"}
    return {"success": False, "ts_code": ts_code, "message": "未找到该股票"}


def add_watch_note(
    conn,
    ts_code: str,
    note: str,
    timestamp: Optional[str] = None,
    source: str = "manual",
    note_type: str = "watch_observation",
) -> dict[str, Any]:
    """添加标的笔记。保留旧函数名以兼容 watchlist 调用。"""
    _, _, exchange = parse_ts_code(ts_code)
    if source.startswith("holding_review") and note_type == "watch_observation":
        note_type = "holding_review"
    return add_note(
        conn,
        ts_code,
        note,
        note_type=note_type,
        timestamp=timestamp,
        source=source,
        exchange=exchange,
    )


def get_watch_notes(conn, ts_code: str, limit: int = 20) -> list[dict[str, Any]]:
    """获取标的笔记。保留旧函数名以兼容调用。"""
    return get_notes(conn, ts_code, limit=limit)


def get_watch_notes_map(conn, ts_codes: list[str], limit: int = 10) -> dict[str, list[dict[str, Any]]]:
    """批量获取标的笔记，按股票代码分组。"""
    return get_notes_map(conn, ts_codes, limit=limit)


def attach_watch_notes(
    watchlist: list[dict[str, Any]],
    notes_map: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """给关注列表附加关注记录，便于 JSON 输出。"""
    result = []
    for item in watchlist:
        row = dict(item)
        row["notes"] = notes_map.get(item["ts_code"], [])
        result.append(row)
    return result


def get_watchlist(
    conn, category: Optional[str] = None, status: Optional[str] = "watching"
) -> list[dict[str, Any]]:
    """获取关注列表"""
    if category and status:
        cursor = conn.execute(
            "SELECT * FROM watchlist WHERE category = ? AND status = ? ORDER BY priority DESC, added_at DESC",
            (category, status),
        )
    elif category:
        cursor = conn.execute(
            "SELECT * FROM watchlist WHERE category = ? ORDER BY priority DESC, added_at DESC",
            (category,),
        )
    elif status:
        cursor = conn.execute(
            "SELECT * FROM watchlist WHERE status = ? ORDER BY priority DESC, added_at DESC",
            (status,),
        )
    else:
        cursor = conn.execute(
            "SELECT * FROM watchlist ORDER BY priority DESC, added_at DESC"
        )
    return [dict(row) for row in cursor.fetchall()]


def get_watch(conn, ts_code: str) -> Optional[dict[str, Any]]:
    """获取单个关注股票"""
    cursor = conn.execute("SELECT * FROM watchlist WHERE ts_code = ?", (ts_code,))
    row = cursor.fetchone()
    return dict(row) if row else None


def get_categories(conn) -> list[str]:
    """获取所有分类"""
    cursor = conn.execute(
        "SELECT DISTINCT category FROM watchlist WHERE status = 'watching' ORDER BY category"
    )
    return [row[0] for row in cursor.fetchall()]


def format_date(value: str) -> str:
    """把 ISO 时间压缩为列表展示用日期。"""
    return (value or "")[:10] or "-"


def format_price(value: Any) -> str:
    return f"{value:.2f}" if value not in (None, "") else "-"


def print_watchlist_table(
    watchlist: list,
    notes_map: Optional[dict[str, list[dict[str, Any]]]] = None,
):
    """按标的分组打印关注列表和多条关注记录。"""
    if not watchlist:
        print("关注列表为空")
        return

    notes_map = notes_map or {}
    priority_names = {0: "普通", 1: "重点", 2: "紧急"}

    print(f"\n关注列表（共 {len(watchlist)} 只）")
    print("=" * 80)

    for index, item in enumerate(watchlist, 1):
        ts_code = item["ts_code"]
        name = item.get("name") or "-"
        category = item.get("category") or "default"
        target = format_price(item.get("target_price"))
        stop = format_price(item.get("stop_loss"))
        priority = priority_names.get(item.get("priority", 0), "普通")
        status = item.get("status") or "watching"
        print(
            f"{index}. {ts_code} {name} | {category} | 目标 {target} | 止损 {stop} | {priority} | {status}"
        )

        notes = notes_map.get(ts_code, [])
        if notes:
            for note in notes:
                print(
                    f"   - {format_date(note.get('timestamp'))} "
                    f"[{note.get('note_type') or '-'}] {note.get('note') or '-'}"
                )
        else:
            print("   - 暂无笔记")
    print("=" * 80)


def print_watch_detail(item: dict, notes: Optional[list[dict[str, Any]]] = None):
    """打印单个关注股票详情"""
    priority_names = {0: "普通", 1: "重点 ⭐", 2: "紧急 🔥"}

    print(f"\n{'='*50}")
    print(f"  股票代码: {item['ts_code']}")
    print(f"{'='*50}")
    print(f"  名称:     {item.get('name') or '-'}")
    print(f"  交易所:   {item.get('exchange') or '-'}")
    print(f"  分类:     {item.get('category') or 'default'}")
    print(f"  优先级:   {priority_names.get(item.get('priority', 0), '普通')}")
    print(f"  状态:     {item.get('status') or 'watching'}")
    print(f"  目标价:   {item['target_price']:.2f}" if item.get("target_price") else "  目标价:   -")
    print(f"  止损价:   {item['stop_loss']:.2f}" if item.get("stop_loss") else "  止损价:   -")
    print(f"  添加时间: {item.get('added_at', '')[:19]}")
    print(f"  更新时间: {item.get('updated_at', '')[:19]}")
    print("  笔记:")
    notes = notes or []
    if notes:
        for note in notes:
            print(
                f"    - {format_date(note.get('timestamp'))} "
                f"[{note.get('note_type') or '-'}] {note.get('note') or '-'}"
            )
    else:
        print("    - 暂无笔记")
    print(f"{'='*50}\n")


def print_watch_notes(notes: list[dict[str, Any]]):
    """打印标的笔记"""
    if not notes:
        print("暂无笔记")
        return
    print(f"\n{'='*80}")
    print(f"  {'时间':<19} {'类型':<18} {'笔记'}")
    print(f"{'='*80}")
    for item in notes:
        print(
            f"  {(item.get('timestamp') or '')[:19]:<19} "
            f"{(item.get('note_type') or '-'):<18} {item.get('note') or '-'}"
        )
    print(f"{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(description="关注列表管理工具")
    parser.add_argument(
        "--workspace",
        default=os.path.expanduser(os.environ.get("STJ_WORKSPACE", "~/.trade-journal")),
        help="工作目录 (默认: STJ_WORKSPACE 或 ~/.trade-journal)",
    )

    subparsers = parser.add_subparsers(dest="command", help="命令")

    # add 命令
    add_parser = subparsers.add_parser("add", help="添加关注")
    add_parser.add_argument("ts_code", help="股票代码 (如 NVDA.US, 0700.HK)")
    add_parser.add_argument("--name", default="", help="股票名称")
    add_parser.add_argument("--category", "-c", default="default", help="分类")
    add_parser.add_argument("--target", "-t", type=float, help="目标价")
    add_parser.add_argument("--stop", "-s", type=float, help="止损价")
    add_parser.add_argument("--reason", "-r", default="", help=argparse.SUPPRESS)
    add_parser.add_argument(
        "--priority", "-p", type=int, default=0, choices=[0, 1, 2], help="优先级 (0=普通, 1=重点, 2=紧急)"
    )
    add_parser.add_argument("--note", "-n", default="", help="关注记录笔记")

    # note 命令
    note_parser = subparsers.add_parser("note", help="添加标的笔记")
    note_parser.add_argument("ts_code", help="股票代码")
    note_parser.add_argument("--note", "-n", required=True, help="笔记内容")
    note_parser.add_argument(
        "--type",
        dest="note_type",
        default="watch_observation",
        choices=NOTE_TYPES,
        help="笔记类型",
    )
    note_parser.add_argument("--timestamp", help="记录时间，默认当前时间")
    note_parser.add_argument("--source", default="manual", help="来源")

    # notes 命令
    notes_parser = subparsers.add_parser("notes", help="查看标的笔记")
    notes_parser.add_argument("ts_code", help="股票代码")
    notes_parser.add_argument("--limit", type=int, default=20, help="最多显示 N 条")
    notes_parser.add_argument("--type", dest="note_type", choices=NOTE_TYPES, help="只显示指定类型")
    notes_parser.add_argument("--json", action="store_true", help="JSON 格式输出")

    # remove 命令
    rm_parser = subparsers.add_parser("remove", aliases=["rm"], help="删除关注")
    rm_parser.add_argument("ts_code", help="股票代码")

    # update 命令
    up_parser = subparsers.add_parser("update", aliases=["up"], help="更新关注")
    up_parser.add_argument("ts_code", help="股票代码")
    up_parser.add_argument("--name", help="股票名称")
    up_parser.add_argument("--category", "-c", help="分类")
    up_parser.add_argument("--target", "-t", type=float, help="目标价")
    up_parser.add_argument("--stop", "-s", type=float, help="止损价")
    up_parser.add_argument("--reason", "-r", help=argparse.SUPPRESS)
    up_parser.add_argument("--priority", "-p", type=int, choices=[0, 1, 2], help="优先级")
    up_parser.add_argument("--status", choices=["watching", "bought", "removed"], help="状态")
    up_parser.add_argument("--note", "-n", help="关注记录笔记")

    # list 命令
    ls_parser = subparsers.add_parser("list", aliases=["ls"], help="查看关注列表")
    ls_parser.add_argument("--category", "-c", help="按分类筛选")
    ls_parser.add_argument("--all", "-a", action="store_true", help="显示所有状态")
    ls_parser.add_argument("--notes-limit", type=int, default=10, help="每只股票显示最近 N 条关注记录")
    ls_parser.add_argument("--json", action="store_true", help="JSON 格式输出")

    # show 命令
    show_parser = subparsers.add_parser("show", help="查看单个股票详情")
    show_parser.add_argument("ts_code", help="股票代码")
    show_parser.add_argument("--notes-limit", type=int, default=20, help="显示最近 N 条关注记录")
    show_parser.add_argument("--json", action="store_true", help="JSON 格式输出")

    # categories 命令
    subparsers.add_parser("categories", aliases=["cats"], help="查看所有分类")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 连接数据库
    base = os.path.join(args.workspace, "results", "trade-journal")
    db_path = os.path.join(base, "db", "trades.db")
    conn = ensure_db(db_path)

    # 执行命令
    if args.command == "add":
        result = add_watch(
            conn,
            args.ts_code,
            name=args.name,
            category=args.category,
            target_price=args.target,
            stop_loss=args.stop,
            priority=args.priority,
        )
        note_text = "；".join(part for part in (args.reason, args.note) if part)
        if note_text:
            add_watch_note(conn, args.ts_code, note_text, source="watchlist_add")
        icon = "✅" if result["success"] else "⚠️"
        print(f"{icon} {result['message']}: {result['ts_code']}")

    elif args.command == "note":
        result = add_watch_note(
            conn,
            args.ts_code,
            note=args.note,
            timestamp=args.timestamp,
            source=args.source,
            note_type=args.note_type,
        )
        icon = "✅" if result["success"] else "⚠️"
        print(f"{icon} {result['message']}: {result['ts_code']}")

    elif args.command == "notes":
        notes = (
            get_notes(conn, args.ts_code, note_type=args.note_type, limit=args.limit)
            if args.note_type
            else get_watch_notes(conn, args.ts_code, args.limit)
        )
        if args.json:
            print(json.dumps(notes, indent=2, ensure_ascii=False))
        else:
            print_watch_notes(notes)

    elif args.command in ("remove", "rm"):
        result = remove_watch(conn, args.ts_code)
        icon = "✅" if result["success"] else "⚠️"
        print(f"{icon} {result['message']}")

    elif args.command in ("update", "up"):
        result = update_watch(
            conn,
            args.ts_code,
            name=args.name,
            category=args.category,
            target_price=args.target,
            stop_loss=args.stop,
            priority=args.priority,
            status=args.status,
        )
        note_text = "；".join(part for part in (args.reason, args.note) if part)
        if note_text:
            add_watch_note(conn, args.ts_code, note_text, source="watchlist_update")
        icon = "✅" if result["success"] else "⚠️"
        print(f"{icon} {result['message']}")

    elif args.command in ("list", "ls"):
        status = None if args.all else "watching"
        watchlist = get_watchlist(conn, category=args.category, status=status) if status else get_watchlist(conn, category=args.category)
        notes_map = get_watch_notes_map(conn, [item["ts_code"] for item in watchlist], args.notes_limit)
        output = attach_watch_notes(watchlist, notes_map)
        if args.json:
            print(json.dumps(output, indent=2, ensure_ascii=False))
        else:
            if args.category:
                print(f"\n分类: {args.category}")
            print_watchlist_table(watchlist, notes_map)

    elif args.command == "show":
        item = get_watch(conn, args.ts_code)
        if item:
            notes = get_watch_notes(conn, args.ts_code, args.notes_limit)
            if args.json:
                output = dict(item)
                output["notes"] = notes
                print(json.dumps(output, indent=2, ensure_ascii=False))
            else:
                print_watch_detail(item, notes)
        else:
            print(f"未找到 {args.ts_code}")

    elif args.command in ("categories", "cats"):
        categories = get_categories(conn)
        if categories:
            print("\n分类列表:")
            for cat in categories:
                count = len(get_watchlist(conn, category=cat))
                print(f"  - {cat} ({count})")
            print()
        else:
            print("暂无分类")

    conn.close()


if __name__ == "__main__":
    main()
