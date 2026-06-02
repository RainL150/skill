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

from db_schema import ensure_db, parse_ts_code


def add_watch(
    conn,
    ts_code: str,
    name: str = "",
    category: str = "default",
    target_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    reason: str = "",
    priority: int = 0,
    note: str = "",
) -> dict[str, Any]:
    """添加关注股票"""
    _, _, exchange = parse_ts_code(ts_code)

    try:
        conn.execute(
            """
            INSERT INTO watchlist (
                ts_code, exchange, name, category, target_price, stop_loss,
                reason, priority, note, added_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                ts_code,
                exchange,
                name,
                category,
                target_price,
                stop_loss,
                reason,
                priority,
                note,
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
        "reason",
        "priority",
        "status",
        "note",
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


def get_watchlist(
    conn, category: Optional[str] = None, status: str = "watching"
) -> list[dict[str, Any]]:
    """获取关注列表"""
    if category:
        cursor = conn.execute(
            "SELECT * FROM watchlist WHERE category = ? AND status = ? ORDER BY priority DESC, added_at DESC",
            (category, status),
        )
    else:
        cursor = conn.execute(
            "SELECT * FROM watchlist WHERE status = ? ORDER BY priority DESC, added_at DESC",
            (status,),
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


def print_watchlist_table(watchlist: list, show_all: bool = False):
    """打印关注列表表格"""
    if not watchlist:
        print("关注列表为空")
        return

    priority_icons = {0: "  ", 1: "⭐", 2: "🔥"}

    print(f"\n{'='*100}")
    print(
        f"  {'优先':<4} {'代码':<12} {'名称':<10} {'分类':<10} {'目标价':>10} {'止损':>10} {'关注原因':<20}"
    )
    print(f"{'='*100}")

    for item in watchlist:
        priority = priority_icons.get(item.get("priority", 0), "  ")
        ts_code = item["ts_code"]
        name = (item.get("name") or "")[:10]
        category = (item.get("category") or "default")[:10]
        target = f"{item['target_price']:.2f}" if item.get("target_price") else "-"
        stop = f"{item['stop_loss']:.2f}" if item.get("stop_loss") else "-"
        reason = (item.get("reason") or "")[:20]

        print(
            f"  {priority:<4} {ts_code:<12} {name:<10} {category:<10} {target:>10} {stop:>10} {reason:<20}"
        )

    print(f"{'='*100}")
    print(f"  共 {len(watchlist)} 只股票")
    print(f"{'='*100}\n")


def print_watch_detail(item: dict):
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
    print(f"  关注原因: {item.get('reason') or '-'}")
    print(f"  备注:     {item.get('note') or '-'}")
    print(f"  添加时间: {item.get('added_at', '')[:19]}")
    print(f"  更新时间: {item.get('updated_at', '')[:19]}")
    print(f"{'='*50}\n")


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
    add_parser.add_argument("--reason", "-r", default="", help="关注原因")
    add_parser.add_argument(
        "--priority", "-p", type=int, default=0, choices=[0, 1, 2], help="优先级 (0=普通, 1=重点, 2=紧急)"
    )
    add_parser.add_argument("--note", "-n", default="", help="备注")

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
    up_parser.add_argument("--reason", "-r", help="关注原因")
    up_parser.add_argument("--priority", "-p", type=int, choices=[0, 1, 2], help="优先级")
    up_parser.add_argument("--status", choices=["watching", "bought", "removed"], help="状态")
    up_parser.add_argument("--note", "-n", help="备注")

    # list 命令
    ls_parser = subparsers.add_parser("list", aliases=["ls"], help="查看关注列表")
    ls_parser.add_argument("--category", "-c", help="按分类筛选")
    ls_parser.add_argument("--all", "-a", action="store_true", help="显示所有状态")
    ls_parser.add_argument("--json", action="store_true", help="JSON 格式输出")

    # show 命令
    show_parser = subparsers.add_parser("show", help="查看单个股票详情")
    show_parser.add_argument("ts_code", help="股票代码")
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
            reason=args.reason,
            priority=args.priority,
            note=args.note,
        )
        icon = "✅" if result["success"] else "⚠️"
        print(f"{icon} {result['message']}: {result['ts_code']}")

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
            reason=args.reason,
            priority=args.priority,
            status=args.status,
            note=args.note,
        )
        icon = "✅" if result["success"] else "⚠️"
        print(f"{icon} {result['message']}")

    elif args.command in ("list", "ls"):
        status = None if args.all else "watching"
        watchlist = get_watchlist(conn, category=args.category, status=status) if status else get_watchlist(conn, category=args.category)
        if args.json:
            print(json.dumps(watchlist, indent=2, ensure_ascii=False))
        else:
            if args.category:
                print(f"\n分类: {args.category}")
            print_watchlist_table(watchlist)

    elif args.command == "show":
        item = get_watch(conn, args.ts_code)
        if item:
            if args.json:
                print(json.dumps(item, indent=2, ensure_ascii=False))
            else:
                print_watch_detail(item)
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
