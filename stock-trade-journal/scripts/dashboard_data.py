#!/usr/bin/env python3
"""Structured CLI for the STJ dashboard data and persistence layer."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from dashboard.contracts import DashboardError, envelope, error_envelope
from dashboard.service import DEFAULT_WORKSPACE, DashboardService


def _common_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--workspace",
        default=os.path.expanduser(os.environ.get("STJ_WORKSPACE", DEFAULT_WORKSPACE)),
        help="工作目录 (默认: STJ_WORKSPACE 或 ~/.trade-journal)",
    )
    parser.add_argument("--json", action="store_true", help="输出结构化 JSON（默认即为 JSON）")
    parser.add_argument("--refresh", action="store_true", help="跳过新鲜缓存并主动刷新外部数据")
    return parser


def _read_payload() -> dict[str, Any]:
    raw = sys.stdin.read(1_000_001)
    if len(raw) > 1_000_000:
        raise DashboardError("请求体超过 1MB", code="BODY_TOO_LARGE", status=413, scope="cli")
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DashboardError("stdin 不是有效 JSON", code="INVALID_JSON", status=400, scope="cli") from exc
    if not isinstance(payload, dict):
        raise DashboardError("JSON payload 必须是对象", code="INVALID_JSON", status=400, scope="cli")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="STJ dashboard structured data CLI")
    common = _common_parser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("portfolio", parents=[common])
    sub.add_parser("watchlist", parents=[common])

    stock_context = sub.add_parser("stock-context", parents=[common])
    stock_context.add_argument("code")

    financials = sub.add_parser("stock-financials", parents=[common])
    financials.add_argument("code")
    financials.add_argument("--period", choices=["annual", "quarterly", "q", "quarter"], default="annual")

    flow = sub.add_parser("stock-flow", parents=[common])
    flow.add_argument("code")

    intel = sub.add_parser("stock-intel", parents=[common])
    intel.add_argument("code")
    intel.add_argument("--kind", choices=["all", "news", "report", "filing"], default="all")
    intel.add_argument("--limit", type=int, default=30)

    options = sub.add_parser("stock-options", parents=[common])
    options.add_argument("code")

    daily = sub.add_parser("daily-review", parents=[common])
    daily.add_argument("--market", choices=["A", "HK", "US"], default="A")

    radar = sub.add_parser("intel", parents=[common])
    radar.add_argument("--scope", choices=["all", "holding", "watch", "investment"], default="all")
    radar.add_argument("--market", choices=["all", "A", "HK", "US"], default="all")
    radar.add_argument("--kind", choices=["all", "news", "report", "filing", "investment_news"], default="all")

    sectors = sub.add_parser("sectors", parents=[common])
    sectors.add_argument("--include-archived", action="store_true")

    sector = sub.add_parser("sector", parents=[common])
    sector.add_argument("sector_id", type=int)

    mutation = sub.add_parser("sector-mutate", parents=[common])
    mutation.add_argument("action", choices=[
        "create", "update", "archive", "tag-add", "tag-delete", "node-add", "node-update", "node-delete",
        "edge-add", "edge-delete", "symbol-add", "symbol-delete", "knowledge-add", "knowledge-update", "knowledge-delete",
    ])

    sub.add_parser("research-save", parents=[common])
    records = sub.add_parser("research-list", parents=[common])
    records.add_argument("--scope-type", choices=["page", "portfolio", "symbol", "sector"])
    records.add_argument("--ts-code")
    records.add_argument("--sector-id", type=int)
    records.add_argument("--limit", type=int, default=50)
    sub.add_parser("research-delete", parents=[common])
    sub.add_parser("ai-capabilities", parents=[common])
    return parser


def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    service = DashboardService(args.workspace)
    if args.command == "portfolio":
        return service.portfolio(args.refresh)
    if args.command == "watchlist":
        return service.watchlist(args.refresh)
    if args.command == "stock-context":
        return service.stock_context(args.code)
    if args.command == "stock-financials":
        return service.financials(args.code, args.period)
    if args.command == "stock-flow":
        return service.flow(args.code)
    if args.command == "stock-intel":
        return service.stock_intel(args.code, args.kind, max(1, min(args.limit, 100)))
    if args.command == "stock-options":
        return service.options(args.code)
    if args.command == "daily-review":
        return service.daily_review(args.market, args.refresh)
    if args.command == "intel":
        return service.intel_radar(args.scope, args.market, args.kind)
    if args.command == "sectors":
        return service.sectors(args.include_archived)
    if args.command == "sector":
        return service.sector(args.sector_id)
    if args.command == "sector-mutate":
        return service.mutate_sector(args.action, _read_payload())
    if args.command == "research-save":
        return service.save_research_record(_read_payload())
    if args.command == "research-list":
        return service.research_records(
            scope_type=args.scope_type,
            ts_code=args.ts_code,
            sector_id=args.sector_id,
            limit=max(1, min(args.limit, 200)),
        )
    if args.command == "research-delete":
        payload = _read_payload()
        return service.delete_research_records(
            record_id=payload.get("record_id"),
            clear_all=payload.get("all") is True,
        )
    if args.command == "ai-capabilities":
        from dashboard.ai.catalog import catalog
        from dashboard.ai.cli_runtime import capability_status

        return envelope(catalog(capability_status()), sources=[{"name": "STJ local capability probe"}])
    raise DashboardError("unknown command", code="INVALID_ACTION", status=400, scope="cli")


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = dispatch(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    except DashboardError as exc:
        print(json.dumps(error_envelope(exc), ensure_ascii=False, indent=2))
        return 1
    except Exception as exc:  # Stable public error; opt-in debug keeps tracebacks out of Node responses.
        if os.environ.get("STJ_DEBUG") == "1":
            raise
        error = DashboardError("数据服务内部错误", code="INTERNAL_ERROR", status=500, scope="cli")
        payload = error_envelope(error)
        payload["meta"]["warnings"] = [str(exc)]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
