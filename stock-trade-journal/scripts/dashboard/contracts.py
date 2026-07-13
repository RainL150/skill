"""Stable response and domain contracts for the STJ dashboard."""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any

from db_schema import parse_ts_code


CONTRACT_VERSION = "dashboard-v1"
MARKET_GROUPS = ("A", "HK", "US")


class DashboardError(RuntimeError):
    """Expected error that can safely cross the HTTP boundary."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "DASHBOARD_ERROR",
        status: int = 500,
        retryable: bool = False,
        scope: str = "dashboard",
        provider: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.retryable = retryable
        self.scope = scope
        self.provider = provider

    def as_item(self) -> dict[str, Any]:
        return error_item(
            self.scope,
            self.code,
            str(self),
            retryable=self.retryable,
            provider=self.provider,
        )


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def finite_number(value: Any) -> float | int | None:
    """Normalize provider numbers while preserving genuine zero values."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = value
    else:
        text = str(value).strip().replace(",", "")
        if not text or text in {"-", "--", "null", "None", "nan", "NaN"}:
            return None
        try:
            number = float(text)
        except (TypeError, ValueError):
            return None
    if isinstance(number, float) and not math.isfinite(number):
        return None
    return number


def json_safe(value: Any) -> Any:
    """Recursively remove NaN/Infinity and non-JSON scalar surprises."""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return finite_number(value)
    if isinstance(value, (str, bool)) or value is None:
        return value
    return str(value)


def market_group(ts_code: str) -> str:
    """Map an STJ code to the user-facing A/HK/US groups."""
    _, market, _ = parse_ts_code(ts_code.strip().upper())
    if market in {"SH", "SZ"}:
        return "A"
    if market in {"HK", "US"}:
        return market
    raise DashboardError(
        f"不支持的市场代码：{ts_code}",
        code="INVALID_SYMBOL",
        status=400,
        scope="symbol",
    )


def normalize_ts_code(ts_code: str) -> str:
    value = (ts_code or "").strip().upper()
    symbol, market, _ = parse_ts_code(value)
    if not symbol or market not in {"SH", "SZ", "HK", "US"}:
        raise DashboardError(
            f"无效代码：{ts_code}",
            code="INVALID_SYMBOL",
            status=400,
            scope="symbol",
        )
    if len(value) > 32 or not all(ch.isalnum() or ch in {".", "-", "_"} for ch in value):
        raise DashboardError(
            f"无效代码：{ts_code}",
            code="INVALID_SYMBOL",
            status=400,
            scope="symbol",
        )
    return value


def asset_ref(
    ts_code: str,
    *,
    name: str | None = None,
    exchange: str | None = None,
    currency: str | None = None,
) -> dict[str, Any]:
    code = normalize_ts_code(ts_code)
    symbol, _, inferred_exchange = parse_ts_code(code)
    group = market_group(code)
    default_currency = {"A": "CNY", "HK": "HKD", "US": "USD"}[group]
    return {
        "ts_code": code,
        "symbol": symbol,
        "name": name or code,
        "market_group": group,
        "exchange": exchange or inferred_exchange,
        "currency": (currency or default_currency).upper(),
    }


def error_item(
    scope: str,
    code: str,
    message: str,
    *,
    retryable: bool = False,
    provider: str | None = None,
) -> dict[str, Any]:
    return {
        "scope": scope,
        "provider": provider,
        "code": code,
        "message": message,
        "retryable": bool(retryable),
    }


def envelope(
    data: Any,
    *,
    ok: bool = True,
    as_of: str | None = None,
    market: str | None = None,
    sources: list[dict[str, Any]] | None = None,
    cache: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    errors: list[dict[str, Any]] | None = None,
    status: int = 200,
) -> dict[str, Any]:
    """Build the only response shape consumed by Node and the browser."""
    generated_at = utc_now()
    return json_safe({
        "ok": bool(ok),
        "data": data,
        "meta": {
            "request_id": str(uuid.uuid4()),
            "contract_version": CONTRACT_VERSION,
            "generated_at": generated_at,
            "as_of": as_of or generated_at,
            "market": market,
            "sources": sources or [],
            "cache": cache or {"hit": False, "stale": False, "age_seconds": 0},
            "warnings": warnings or [],
            "status": status,
        },
        "errors": errors or [],
    })


def error_envelope(error: DashboardError) -> dict[str, Any]:
    return envelope(
        None,
        ok=False,
        errors=[error.as_item()],
        warnings=[str(error)],
        status=error.status,
    )
