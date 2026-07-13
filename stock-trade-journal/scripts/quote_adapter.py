#!/usr/bin/env python3
"""
Unified quote adapter for stock-trade-journal.

The adapter returns one stable shape for A-share, HK, US, and simple FX quotes:
symbol, price, currency, quote_time, source, and CNY conversion rate.  It is
intentionally conservative: failed quotes are explicit errors, never silent
stale values.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any


USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
YAHOO_CHART_URLS = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
    "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}",
)
FX_SYMBOLS = {
    "CNY": None,
    "USD": "CNY=X",
    "HKD": "HKDCNY=X",
}


def yahoo_symbol(ts_code: str) -> str:
    """Map local STJ symbols to Yahoo Finance symbols."""
    value = ts_code.strip().upper()
    if value.endswith(".SH"):
        return f"{value[:-3]}.SS"
    if value.endswith(".SZ"):
        return value
    if value.endswith(".HK"):
        code = value[:-3]
        if code.isdigit():
            code = code.zfill(4)
        return f"{code}.HK"
    if value.endswith(".US"):
        return value[:-3]
    return value


def _utc_iso(timestamp: int | float | None) -> str | None:
    if not timestamp:
        return None
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).isoformat()


def _latest_non_null(values: list[Any]) -> int | None:
    for index in range(len(values) - 1, -1, -1):
        if values[index] is not None:
            return index
    return None


def fetch_yahoo_chart(symbol: str, range_: str = "10d", interval: str = "1d") -> dict[str, Any]:
    params = urllib.parse.urlencode({
        "range": range_,
        "interval": interval,
        "includePrePost": "false",
        "events": "div,splits",
    })
    last_error: Exception | None = None
    payload = None
    for attempt in range(3):
        for template in YAHOO_CHART_URLS:
            url = f"{template.format(symbol=urllib.parse.quote(symbol))}?{params}"
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=12) as response:
                    payload = json.load(response)
                break
            except Exception as exc:  # noqa: BLE001 - try the alternate Yahoo host.
                last_error = exc
        if payload is not None:
            break
        time.sleep(0.4 * (attempt + 1))
    if payload is None:
        raise RuntimeError(str(last_error) if last_error else "Yahoo chart request failed")

    error = payload.get("chart", {}).get("error")
    if error:
        raise RuntimeError(error.get("description") or str(error))

    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError("empty Yahoo chart result")

    meta = result.get("meta") or {}
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    latest_index = _latest_non_null(closes)
    if latest_index is None:
        raise RuntimeError("no valid close in Yahoo chart result")

    regular_price = meta.get("regularMarketPrice")
    close_price = closes[latest_index]
    price = regular_price if regular_price is not None else close_price

    return {
        "yahoo_symbol": symbol,
        "name": meta.get("shortName") or meta.get("longName") or meta.get("symbol") or symbol,
        "currency": meta.get("currency"),
        "exchange": meta.get("exchangeName"),
        "price": price,
        "close": close_price,
        "previous_close": meta.get("chartPreviousClose"),
        "regular_market_time": _utc_iso(meta.get("regularMarketTime")),
        "bar_time": _utc_iso(timestamps[latest_index] if latest_index < len(timestamps) else None),
        "timezone": meta.get("timezone"),
        "gmtoffset": meta.get("gmtoffset"),
        "source": "Yahoo Finance chart API",
        "source_url": f"https://finance.yahoo.com/quote/{urllib.parse.quote(symbol)}",
    }


def fetch_quote(ts_code: str) -> dict[str, Any]:
    symbol = yahoo_symbol(ts_code)
    try:
        data = fetch_yahoo_chart(symbol)
        data.update({
            "ts_code": ts_code,
            "ok": True,
            "error": None,
        })
        return data
    except Exception as exc:  # noqa: BLE001 - explicit quote failures are data.
        return {
            "ts_code": ts_code,
            "yahoo_symbol": symbol,
            "ok": False,
            "error": str(exc),
            "source": "Yahoo Finance chart API",
        }


def fetch_fx_rates(currencies: set[str]) -> dict[str, dict[str, Any]]:
    """Return CNY conversion rates for currencies in use."""
    result: dict[str, dict[str, Any]] = {
        "CNY": {
            "currency": "CNY",
            "cny_rate": 1.0,
            "ok": True,
            "source": "identity",
        }
    }
    for currency in sorted(currencies):
        currency = (currency or "").upper()
        if currency in result:
            continue
        fx_symbol = FX_SYMBOLS.get(currency)
        if not fx_symbol:
            result[currency] = {
                "currency": currency,
                "cny_rate": None,
                "ok": False,
                "error": "unsupported currency",
            }
            continue
        quote = fetch_quote(fx_symbol)
        result[currency] = {
            "currency": currency,
            "cny_rate": quote.get("price") if quote.get("ok") else None,
            "quote_time": quote.get("regular_market_time") or quote.get("bar_time"),
            "ok": bool(quote.get("ok")),
            "error": quote.get("error"),
            "source": quote.get("source"),
            "source_symbol": fx_symbol,
        }
    return result


def fetch_quotes_many(ts_codes: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch independent Yahoo quotes concurrently without adding FX data."""
    quotes: dict[str, dict[str, Any]] = {}
    # Yahoo occasionally drops SSL handshakes under higher parallelism. Four
    # workers keeps portfolio snapshots fast without making failures common.
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(ts_codes)))) as executor:
        futures = {executor.submit(fetch_quote, ts_code): ts_code for ts_code in ts_codes}
        for future in as_completed(futures):
            ts_code = futures[future]
            try:
                quotes[ts_code] = future.result()
            except Exception as exc:  # noqa: BLE001 - keep one bad symbol from killing the pack.
                quotes[ts_code] = {
                    "ts_code": ts_code,
                    "yahoo_symbol": yahoo_symbol(ts_code),
                    "ok": False,
                    "error": str(exc),
                    "source": "Yahoo Finance chart API",
                }
    return quotes


def quote_many(ts_codes: list[str]) -> dict[str, Any]:
    quotes = fetch_quotes_many(ts_codes)
    currencies = {
        str(item.get("currency") or "").upper()
        for item in quotes.values()
        if item.get("ok") and item.get("currency")
    }
    fx_rates = fetch_fx_rates(currencies)
    for quote in quotes.values():
        currency = str(quote.get("currency") or "").upper()
        rate = fx_rates.get(currency, {})
        quote["cny_rate"] = rate.get("cny_rate")
        quote["cny_rate_source"] = rate.get("source")
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "policy": "Yahoo chart quotes; CNY weights are estimates; failed quotes are explicit errors.",
        "quotes": quotes,
        "fx_rates": fx_rates,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch normalized quotes for STJ symbols")
    parser.add_argument("symbols", nargs="+", help="STJ symbols, e.g. 002803.SZ 0700.HK NVDA.US")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    data = quote_many(args.symbols)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    for ts_code, quote in data["quotes"].items():
        if not quote.get("ok"):
            print(f"{ts_code}: quote failed: {quote.get('error')}")
            continue
        quote_time = quote.get("regular_market_time") or quote.get("bar_time") or "-"
        print(
            f"{ts_code}: {quote.get('price')} {quote.get('currency')} "
            f"@ {quote_time} ({quote.get('source')})"
        )


if __name__ == "__main__":
    main()
