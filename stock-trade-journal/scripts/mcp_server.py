#!/usr/bin/env python3
"""
Minimal MCP server for stock-trade-journal.

It exposes local journal data as objective tools.  Analysis and trading
decisions remain in the calling agent / STJ skill flow.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from db_schema import ensure_db, get_notes, get_positions
from evidence_pack import build_pack
from quote_adapter import quote_many


SERVER_INFO = {"name": "stock-trade-journal", "version": "0.1.0"}
DEFAULT_PROTOCOL = "2024-11-05"
DEFAULT_WORKSPACE = os.path.expanduser(os.environ.get("STJ_WORKSPACE", "~/.trade-journal"))


TOOLS = [
    {
        "name": "stj_query_positions",
        "description": "Read current local STJ positions from SQLite. Returns objective local data only.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace": {"type": "string", "description": "Optional STJ workspace path"}
            },
        },
    },
    {
        "name": "stj_query_notes",
        "description": "Read recent notes for one STJ symbol.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ts_code": {"type": "string", "description": "Symbol such as RDDT.US or 002803.SZ"},
                "limit": {"type": "integer", "default": 10},
                "workspace": {"type": "string", "description": "Optional STJ workspace path"},
            },
            "required": ["ts_code"],
        },
    },
    {
        "name": "stj_quote",
        "description": "Fetch normalized quotes for STJ symbols with quote time, currency, source, and CNY conversion rate.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["symbols"],
        },
    },
    {
        "name": "stj_evidence_pack",
        "description": "Build a portfolio/watchlist evidence pack with local context, quotes, weights, and combined exposures.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace": {"type": "string", "description": "Optional STJ workspace path"}
            },
        },
    },
]


def _send(obj: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _result(rid: Any, result: Any) -> None:
    _send({"jsonrpc": "2.0", "id": rid, "result": result})


def _error(rid: Any, code: int, message: str) -> None:
    _send({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}})


def _db_path(workspace: str) -> str:
    return os.path.join(os.path.expanduser(workspace), "results", "trade-journal", "db", "trades.db")


def _exec_tool(name: str, args: dict[str, Any]) -> Any:
    workspace = args.get("workspace") or DEFAULT_WORKSPACE
    if name == "stj_query_positions":
        conn = ensure_db(_db_path(workspace))
        try:
            return get_positions(conn)
        finally:
            conn.close()
    if name == "stj_query_notes":
        conn = ensure_db(_db_path(workspace))
        try:
            return get_notes(conn, str(args["ts_code"]), limit=int(args.get("limit") or 10))
        finally:
            conn.close()
    if name == "stj_quote":
        return quote_many([str(symbol) for symbol in args.get("symbols", [])])
    if name == "stj_evidence_pack":
        return build_pack(workspace)
    return {"error": f"unknown tool: {name}"}


def _handle(msg: dict[str, Any]) -> None:
    method = msg.get("method")
    rid = msg.get("id")

    if method == "notifications/initialized":
        return
    if method == "initialize":
        proto = (msg.get("params") or {}).get("protocolVersion", DEFAULT_PROTOCOL)
        _result(rid, {
            "protocolVersion": proto,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })
        return
    if method == "ping":
        _result(rid, {})
        return
    if method == "tools/list":
        _result(rid, {"tools": TOOLS})
        return
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name", "")
        args = params.get("arguments") or {}
        try:
            data = _exec_tool(name, args)
            is_error = isinstance(data, dict) and "error" in data
        except Exception as exc:  # noqa: BLE001 - return structured MCP errors.
            data = {"error": str(exc)}
            is_error = True
        _result(rid, {
            "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
            "isError": is_error,
        })
        return
    if rid is not None:
        _error(rid, -32601, f"unknown method: {method}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        _handle(msg)


if __name__ == "__main__":
    main()
