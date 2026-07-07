#!/usr/bin/env python3
"""
Build a structured evidence pack for portfolio and watchlist analysis.

This is the data layer counterpart to the prose-heavy STJ analysis flow.  It
collects local positions, watchlist, recent notes, normalized quotes, estimated
CNY weights, and same-company exposure hints into one JSON artifact.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from typing import Any

from db_schema import ensure_db, get_notes_map, get_positions
from quote_adapter import quote_many


DEFAULT_WORKSPACE = os.path.expanduser(os.environ.get("STJ_WORKSPACE", "~/.trade-journal"))
SAME_COMPANY_ALIASES = {
    "002803.SZ": "Jihong",
    "2603.HK": "Jihong",
}


def workspace_paths(workspace: str) -> dict[str, str]:
    base = os.path.join(workspace, "results", "trade-journal")
    return {
        "base": base,
        "db": os.path.join(base, "db", "trades.db"),
        "snapshots": os.path.join(base, "snapshots"),
    }


def load_watchlist(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM watchlist
        WHERE status != 'removed'
        ORDER BY priority DESC, added_at DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def exposure_key(ts_code: str) -> str:
    return SAME_COMPANY_ALIASES.get(ts_code, ts_code)


def enrich_positions(positions: list[dict[str, Any]], quotes: dict[str, Any]) -> tuple[list[dict[str, Any]], float]:
    rows: list[dict[str, Any]] = []
    total_cny = 0.0
    for pos in positions:
        ts_code = pos["ts_code"]
        quote = quotes.get(ts_code, {})
        quantity = pos.get("quantity") or 0
        avg_cost = pos.get("avg_cost") or 0.0
        local_currency = pos.get("currency") or quote.get("currency") or "CNY"
        price = quote.get("price") if quote.get("ok") else None
        market_value = price * quantity if price is not None else None
        total_cost = avg_cost * quantity
        unrealized_pnl = market_value - total_cost if market_value is not None else None
        unrealized_pnl_pct = (unrealized_pnl / total_cost * 100) if unrealized_pnl is not None and total_cost else None
        cny_rate = quote.get("cny_rate")
        cny_market_value = market_value * cny_rate if market_value is not None and cny_rate else None
        if cny_market_value:
            total_cny += cny_market_value
        rows.append({
            "ts_code": ts_code,
            "exchange": pos.get("exchange"),
            "quantity": quantity,
            "avg_cost": avg_cost,
            "currency": local_currency,
            "quote": quote,
            "market_value": market_value,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "cny_market_value_est": cny_market_value,
            "exposure_key": exposure_key(ts_code),
            "first_buy_date": pos.get("first_buy_date"),
            "last_trade_date": pos.get("last_trade_date"),
        })
    for row in rows:
        value = row.get("cny_market_value_est")
        row["cny_weight_est"] = value / total_cny * 100 if value and total_cny else None
    return rows, total_cny


def build_combined_exposure(position_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for row in position_rows:
        key = row["exposure_key"]
        group = groups.setdefault(key, {
            "exposure_key": key,
            "symbols": [],
            "cny_market_value_est": 0.0,
            "cny_weight_est": 0.0,
            "unconfirmed_symbols": [],
        })
        group["symbols"].append(row["ts_code"])
        value = row.get("cny_market_value_est")
        if value is None:
            group["unconfirmed_symbols"].append(row["ts_code"])
        else:
            group["cny_market_value_est"] += value
            group["cny_weight_est"] += row.get("cny_weight_est") or 0.0
    return sorted(groups.values(), key=lambda item: item["cny_market_value_est"], reverse=True)


def enrich_watchlist(watchlist: list[dict[str, Any]], notes_map: dict[str, list[dict[str, Any]]], quotes: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in watchlist:
        ts_code = item["ts_code"]
        quote = quotes.get(ts_code, {})
        target = item.get("target_price")
        price = quote.get("price") if quote.get("ok") else None
        distance_to_target_pct = ((price - target) / target * 100) if price is not None and target else None
        rows.append({
            **item,
            "quote": quote,
            "distance_to_target_pct": distance_to_target_pct,
            "recent_notes": notes_map.get(ts_code, []),
        })
    return rows


def build_pack(workspace: str = DEFAULT_WORKSPACE) -> dict[str, Any]:
    paths = workspace_paths(os.path.expanduser(workspace))
    if not os.path.exists(paths["db"]):
        raise FileNotFoundError(f"database not found: {paths['db']}")

    conn = ensure_db(paths["db"])
    try:
        positions = get_positions(conn)
        watchlist = load_watchlist(conn)
        ts_codes = sorted({row["ts_code"] for row in positions + watchlist})
        quote_payload = quote_many(ts_codes) if ts_codes else {"quotes": {}, "fx_rates": {}}
        quotes = quote_payload.get("quotes", {})
        notes_map = get_notes_map(conn, ts_codes, limit=5) if ts_codes else {}
        position_rows, total_cny = enrich_positions(positions, quotes)
        return {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "workspace": os.path.expanduser(workspace),
            "quote_policy": quote_payload.get("policy"),
            "fx_rates": quote_payload.get("fx_rates", {}),
            "positions": position_rows,
            "watchlist": enrich_watchlist(watchlist, notes_map, quotes),
            "combined_exposure": build_combined_exposure(position_rows),
            "totals": {
                "cny_market_value_est": total_cny,
                "cash_not_included": True,
                "weights_are_estimates": True,
            },
        }
    finally:
        conn.close()


def write_snapshot(pack: dict[str, Any], workspace: str, name: str | None = None) -> str:
    paths = workspace_paths(os.path.expanduser(workspace))
    os.makedirs(paths["snapshots"], exist_ok=True)
    filename = name or dt.datetime.now().strftime("%Y-%m-%d-evidence-pack.json")
    path = os.path.join(paths["snapshots"], filename)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(pack, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def print_summary(pack: dict[str, Any]) -> None:
    total = pack["totals"]["cny_market_value_est"]
    print(f"证据包生成时间: {pack['generated_at']}")
    print(f"持仓数量: {len(pack['positions'])} | 关注数量: {len(pack['watchlist'])}")
    print(f"组合市值粗估: {total:,.0f} CNY（未纳入现金）")
    print("\n合并暴露:")
    for item in pack["combined_exposure"][:10]:
        suffix = ""
        if item.get("unconfirmed_symbols"):
            suffix = f" | 未确认: {', '.join(item['unconfirmed_symbols'])}"
        print(
            f"- {item['exposure_key']}: {', '.join(item['symbols'])} | "
            f"{item['cny_market_value_est']:,.0f} CNY | {item['cny_weight_est']:.1f}%"
            f"{suffix}"
        )

    unconfirmed = [
        row["ts_code"]
        for row in pack["positions"]
        if not row.get("quote", {}).get("ok")
    ]
    if unconfirmed:
        print("\n行情未确认（不计入权重）:")
        for ts_code in unconfirmed:
            print(f"- {ts_code}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build STJ portfolio/watchlist evidence pack")
    parser.add_argument(
        "--workspace",
        default=DEFAULT_WORKSPACE,
        help="工作目录 (默认: STJ_WORKSPACE 或 ~/.trade-journal)",
    )
    parser.add_argument("--json", action="store_true", help="Output full JSON")
    parser.add_argument("--write", action="store_true", help="Write snapshot JSON under results/trade-journal/snapshots")
    parser.add_argument("--name", help="Snapshot filename when --write is used")
    args = parser.parse_args()

    pack = build_pack(args.workspace)
    if args.write:
        path = write_snapshot(pack, args.workspace, args.name)
        pack["snapshot_path"] = path
    if args.json:
        print(json.dumps(pack, ensure_ascii=False, indent=2))
    else:
        print_summary(pack)
        if args.write:
            print(f"\n已写入: {pack['snapshot_path']}")


if __name__ == "__main__":
    main()
