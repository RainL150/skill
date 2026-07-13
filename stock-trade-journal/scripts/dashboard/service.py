"""Application service that joins STJ facts with cross-market providers."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from db_schema import (
    add_research_record,
    add_sector_edge,
    add_sector_knowledge,
    add_sector_node,
    add_sector_symbol,
    add_sector_tag,
    archive_sector,
    create_sector,
    clear_research_records,
    delete_research_record,
    delete_sector_edge,
    delete_sector_knowledge,
    delete_sector_node,
    delete_sector_symbol,
    delete_sector_tag,
    ensure_db,
    get_notes,
    get_notes_map,
    get_position,
    get_positions,
    get_sector,
    get_trades_for_symbol,
    get_watch,
    get_watchlist,
    list_research_records,
    list_sectors,
    update_sector,
    update_sector_knowledge,
    update_sector_node,
)
from evidence_pack import build_combined_exposure, exposure_key
from quote_adapter import fetch_fx_rates
from dashboard.cache import AtomicJsonCache
from dashboard.contracts import (
    DashboardError,
    asset_ref,
    envelope,
    error_item,
    finite_number,
    market_group,
    normalize_ts_code,
    utc_now,
)
from dashboard.providers.a_stock import AStockProvider, risk_tags
from dashboard.providers.base import ProviderError
from dashboard.providers.global_stock import YahooClient


DEFAULT_WORKSPACE = os.path.expanduser(os.environ.get("STJ_WORKSPACE", "~/.trade-journal"))


def _env_ttl(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


TTL = {
    "quote": _env_ttl("STJ_QUOTE_TTL_SECONDS", 180),
    "indices": 60,
    "rotation": 300,
    "profile": 7 * 24 * 3600,
    "valuation": 900,
    "financials": 18 * 3600,
    "flow": 300,
    "options": 300,
    "news": 900,
    "reports": 6 * 3600,
    "filings": 6 * 3600,
}


def workspace_paths(workspace: str) -> dict[str, Path]:
    root = Path(workspace).expanduser()
    base = root / "results" / "trade-journal"
    return {
        "workspace": root,
        "base": base,
        "db": base / "db" / "trades.db",
        "cache": base / "cache" / "dashboard",
    }


def _provider_error(scope: str, exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ProviderError):
        return error_item(
            scope,
            exc.code,
            str(exc),
            retryable=exc.retryable,
            provider=exc.provider,
        )
    if isinstance(exc, DashboardError):
        return exc.as_item()
    return error_item(scope, "UPSTREAM_ERROR", str(exc), retryable=True)


def _dedupe_intel(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for item in items:
        url = str(item.get("source_url") or "").split("?", 1)[0].rstrip("/").lower()
        title = " ".join(str(item.get("title") or "").lower().split())
        date = str(item.get("published_at") or "")[:10]
        key_source = url or f"{title}|{item.get('source_name')}|{date}"
        key = hashlib.sha256(key_source.encode("utf-8")).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        clean = dict(item)
        clean["dedupe_key"] = key
        clean["risk_tags"] = list(dict.fromkeys([*(clean.get("risk_tags") or []), *risk_tags(clean.get("title") or "")]))
        output.append(clean)
    return output


def intel_relevance_score(
    *,
    scope: str,
    holding_weight: float | None = None,
    watch_priority: float | None = None,
    published_at: str | None = None,
    has_risk_tag: bool = False,
) -> float:
    """Named, bounded ranking formula used by the intelligence radar."""
    base = {"holding": 100.0, "watch": 45.0, "investment": 20.0}.get(scope, 0.0)
    portfolio_bonus = min(max(finite_number(holding_weight) or 0.0, 0.0), 100.0)
    watch_bonus = min(max(finite_number(watch_priority) or 0.0, 0.0), 5.0) * 8.0
    age_bonus = 0.0
    if published_at:
        try:
            published = datetime.fromisoformat(str(published_at).replace("Z", "+00:00")).date()
            days = max(0, (datetime.now().date() - published).days)
            age_bonus = 20.0 if days == 0 else 12.0 if days <= 3 else 5.0 if days <= 7 else 0.0
        except ValueError:
            age_bonus = 0.0
    return base + portfolio_bonus + watch_bonus + age_bonus + (15.0 if has_risk_tag else 0.0)


def market_temperature(
    positive_count: Any,
    negative_count: Any,
    flat_count: Any = 0,
    *,
    basis: str,
    proxy: bool = False,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Mechanical market-breadth classification from explicit up/down counts.

    A-share callers provide constituent advance/decline counts. HK/US callers only
    have ETF/index proxies, so the result is labeled as a proxy and never presented
    as whole-market breadth.
    """
    positive = max(0, int(finite_number(positive_count) or 0))
    negative = max(0, int(finite_number(negative_count) or 0))
    flat = max(0, int(finite_number(flat_count) or 0))
    directional = positive + negative
    sample_count = directional + flat
    if directional == 0:
        breadth = "数据不足"
    else:
        ratio = positive / max(negative, 1)
        if not proxy and sample_count >= 2_000 and positive < 600:
            breadth = "冰点"
        elif ratio < 0.7:
            breadth = "偏弱"
        elif ratio < 1.2:
            breadth = "中性"
        elif ratio < 2.5:
            breadth = "偏强"
        else:
            breadth = "普涨"
    return {
        "label": "代理温度" if proxy else "市场宽度",
        "breadth": breadth,
        "positive_count": positive,
        "negative_count": negative,
        "flat_count": flat,
        "sample_count": sample_count,
        "positive_ratio": round(positive / directional * 100, 1) if directional else None,
        "balance_score": round((positive - negative) / directional * 100, 1) if directional else None,
        "basis": basis,
        "metric_kind": "performance_proxy" if proxy else "market_breadth",
        "as_of": as_of,
    }


def _redact_sensitive(value: Any) -> Any:
    """Remove secrets before an explicit research-record write."""
    sensitive = ("api_key", "apikey", "authorization", "token", "secret", "access_key", "backend_access_key")
    if isinstance(value, dict):
        output = {}
        for key, item in value.items():
            if any(marker in str(key).lower() for marker in sensitive):
                output[str(key)] = "[REDACTED]"
            else:
                output[str(key)] = _redact_sensitive(item)
        return output
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value


class DashboardService:
    def __init__(self, workspace: str = DEFAULT_WORKSPACE) -> None:
        self.paths = workspace_paths(workspace)
        self.paths["db"].parent.mkdir(parents=True, exist_ok=True)
        self.cache = AtomicJsonCache(self.paths["cache"])
        self.a_stock = AStockProvider(self.paths["cache"])
        self.yahoo = YahooClient()

    @property
    def workspace(self) -> str:
        return str(self.paths["workspace"])

    @contextmanager
    def connection(self) -> Iterator[Any]:
        conn = ensure_db(str(self.paths["db"]))
        try:
            yield conn
        finally:
            conn.close()

    def _cached(
        self,
        provider: str,
        operation: str,
        params: dict[str, Any],
        ttl_seconds: float,
        loader,
        *,
        force_refresh: bool = False,
    ) -> tuple[Any, dict[str, Any], list[str]]:
        return self.cache.fetch(
            provider,
            operation,
            params,
            ttl_seconds=ttl_seconds,
            loader=loader,
            allow_stale=True,
            force_refresh=force_refresh,
        )

    def _quote(self, ts_code: str) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        code = normalize_ts_code(ts_code)
        group = market_group(code)
        provider = "tencent" if group == "A" else "yahoo"
        if group == "A":
            def load() -> dict[str, Any]:
                result = self.a_stock.quotes([code]).get(code)
                if not result:
                    raise ProviderError("tencent", "QUOTE_UNAVAILABLE", f"未取到 {code} 行情", retryable=True)
                return result
        else:
            load = lambda: self.yahoo.quote(code)
        quote, cache_meta, warnings = self._cached(provider, "quote", {"ts_code": code}, TTL["quote"], load)
        return self._decorate_quote(quote, cache_meta, warnings)

    def _decorate_quote(
        self,
        quote: dict[str, Any],
        cache_meta: dict[str, Any],
        warnings: list[str],
    ) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        asset = quote.get("asset") or {}
        group = str(asset.get("market_group") or "")
        currency = str(asset.get("currency") or {"A": "CNY", "HK": "HKD", "US": "USD"}.get(group) or "CNY")
        if currency == "CNY":
            fx = {"cny_rate": 1.0, "source": "identity", "quote_time": quote.get("quote_time")}
        elif finite_number(quote.get("cny_rate")) is not None:
            fx = {
                "cny_rate": quote.get("cny_rate"),
                "source": quote.get("cny_rate_source") or "Yahoo Finance chart API",
                "quote_time": quote.get("fx_as_of"),
            }
        else:
            fx_payload, fx_cache, fx_warnings = self._cached(
                "yahoo",
                "fx",
                {"currency": currency},
                TTL["quote"],
                lambda: fetch_fx_rates({currency}).get(currency) or {},
            )
            fx = fx_payload
            warnings.extend(fx_warnings)
            cache_meta["fx_hit"] = fx_cache.get("hit")
        output = copy.deepcopy(quote)
        output["cny_rate"] = finite_number(fx.get("cny_rate"))
        output["cny_rate_source"] = fx.get("source")
        output["fx_as_of"] = fx.get("quote_time")
        output["cache"] = cache_meta
        return output, cache_meta, warnings

    def _quotes_many(
        self,
        ts_codes: list[str],
        *,
        force_refresh: bool = False,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, Exception], list[str]]:
        """Load portfolio/watch quotes in provider batches with per-symbol stale fallback."""
        codes = list(dict.fromkeys(normalize_ts_code(code) for code in ts_codes))
        quotes: dict[str, dict[str, Any]] = {}
        failures: dict[str, Exception] = {}
        warnings: list[str] = []
        stale_entries: dict[str, Any] = {}
        pending: dict[str, list[str]] = {"A": [], "GLOBAL": []}

        for code in codes:
            group = market_group(code)
            provider = "tencent" if group == "A" else "yahoo"
            entry = self.cache.get(provider, "quote", {"ts_code": code}, TTL["quote"])
            if entry and entry.fresh and not force_refresh:
                cache_meta = {"hit": True, "stale": False, "age_seconds": round(entry.age_seconds, 3)}
                try:
                    quotes[code], _, quote_warnings = self._decorate_quote(entry.value, cache_meta, [])
                    warnings.extend(quote_warnings)
                except Exception as exc:
                    failures[code] = exc
                continue
            if entry:
                stale_entries[code] = entry
            pending["A" if group == "A" else "GLOBAL"].append(code)

        fetched: dict[str, dict[str, dict[str, Any]]] = {"A": {}, "GLOBAL": {}}
        group_failures: dict[str, Exception] = {}
        jobs = {}
        with ThreadPoolExecutor(max_workers=2) as executor:
            if pending["A"]:
                jobs[executor.submit(self.a_stock.quotes, pending["A"])] = "A"
            if pending["GLOBAL"]:
                jobs[executor.submit(self.yahoo.quotes, pending["GLOBAL"])] = "GLOBAL"
            for future, group in jobs.items():
                try:
                    fetched[group] = future.result()
                except Exception as exc:
                    group_failures[group] = exc

        for group, group_codes in pending.items():
            provider = "tencent" if group == "A" else "yahoo"
            for code in group_codes:
                base = fetched[group].get(code)
                if base:
                    self.cache.set(provider, "quote", {"ts_code": code}, base)
                    cache_meta = {"hit": False, "stale": False, "age_seconds": 0}
                elif code in stale_entries:
                    entry = stale_entries[code]
                    base = entry.value
                    cache_meta = {"hit": True, "stale": True, "age_seconds": round(entry.age_seconds, 3)}
                    warnings.append(f"{code} 实时行情失败，使用 {int(entry.age_seconds)} 秒前缓存")
                else:
                    failures[code] = group_failures.get(group) or ProviderError(
                        provider,
                        "QUOTE_UNAVAILABLE",
                        f"未取到 {code} 行情",
                        retryable=True,
                    )
                    continue
                try:
                    quotes[code], _, quote_warnings = self._decorate_quote(base, cache_meta, [])
                    warnings.extend(quote_warnings)
                except Exception as exc:
                    failures[code] = exc
        return quotes, failures, list(dict.fromkeys(warnings))

    def portfolio(self, force_refresh: bool = False) -> dict[str, Any]:
        with self.connection() as conn:
            positions = get_positions(conn)
            watches = get_watchlist(conn)
            notes_map = get_notes_map(conn, sorted({row["ts_code"] for row in positions + watches}), limit=5)
        watch_map = {row["ts_code"]: row for row in watches}
        rows: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        warnings: list[str] = []
        quote_map, quote_failures, quote_warnings = self._quotes_many(
            [row["ts_code"] for row in positions], force_refresh=force_refresh,
        )
        warnings.extend(quote_warnings)
        total_market_cny = 0.0
        total_pnl_cny = 0.0
        today_pnl_cny = 0.0
        up_count = down_count = 0
        for position in positions:
            code = position["ts_code"]
            quote = quote_map.get(code)
            if quote is None:
                quote = {
                    "asset": asset_ref(code, exchange=position.get("exchange"), currency=position.get("currency")),
                    "last": None,
                    "previous_close": None,
                    "source": "未确认",
                    "stale": False,
                }
                errors.append(_provider_error(f"portfolio.quote.{code}", quote_failures.get(code) or RuntimeError("行情不可用")))
            quantity = finite_number(position.get("quantity")) or 0
            avg_cost = finite_number(position.get("avg_cost"))
            total_cost = finite_number(position.get("total_cost"))
            if total_cost is None and avg_cost is not None:
                total_cost = avg_cost * quantity
            last = finite_number(quote.get("last"))
            previous = finite_number(quote.get("previous_close"))
            rate = finite_number(quote.get("cny_rate"))
            market_value = last * quantity if last is not None else None
            realized = finite_number(position.get("realized_pnl")) or 0
            total_return = market_value - total_cost + realized if market_value is not None and total_cost is not None else None
            return_rate = total_return / total_cost * 100 if total_return is not None and total_cost else None
            market_cny = market_value * rate if market_value is not None and rate is not None else None
            pnl_cny = total_return * rate if total_return is not None and rate is not None else None
            day_pnl = (last - previous) * quantity if last is not None and previous is not None else None
            day_pnl_cny = day_pnl * rate if day_pnl is not None and rate is not None else None
            if market_cny is not None:
                total_market_cny += market_cny
            if pnl_cny is not None:
                total_pnl_cny += pnl_cny
            if day_pnl_cny is not None:
                today_pnl_cny += day_pnl_cny
                if day_pnl_cny > 0:
                    up_count += 1
                elif day_pnl_cny < 0:
                    down_count += 1
            alerts: list[dict[str, Any]] = []
            watch = watch_map.get(code)
            if watch and last is not None:
                target = finite_number(watch.get("target_price"))
                stop = finite_number(watch.get("stop_loss"))
                if target is not None and last >= target:
                    alerts.append({"kind": "target", "message": "已到达关注目标价"})
                if stop is not None and last <= stop:
                    alerts.append({"kind": "stop", "message": "已触及关注止损价"})
            rows.append({
                "asset": quote.get("asset") or asset_ref(code),
                "quantity": quantity,
                "avg_cost": avg_cost,
                "currency": position.get("currency") or (quote.get("asset") or {}).get("currency"),
                "quote": quote,
                "market_value_original": market_value,
                "market_value_cny_est": market_cny,
                "total_return_original": total_return,
                "return_rate": return_rate,
                "today_pnl_original": day_pnl,
                "weight": None,
                "realized_pnl": realized,
                "exposure_key": exposure_key(code),
                "alerts": alerts,
                "recent_notes": notes_map.get(code, []),
                "first_buy_date": position.get("first_buy_date"),
                "last_trade_date": position.get("last_trade_date"),
                "data_status": "stale" if quote.get("cache", {}).get("stale") else "ok" if last is not None else "unavailable",
            })
        for row in rows:
            value = row.get("market_value_cny_est")
            row["weight"] = value / total_market_cny * 100 if value is not None and total_market_cny else None
        combined_rows = [
            {
                "ts_code": row["asset"]["ts_code"],
                "exposure_key": row["exposure_key"],
                "cny_market_value_est": row.get("market_value_cny_est"),
                "cny_weight_est": row.get("weight"),
            }
            for row in rows
        ]
        return envelope(
            {
                "summary": {
                    "total_market_value_cny_est": total_market_cny,
                    "total_pnl_cny_est": total_pnl_cny,
                    "today_pnl_cny_est": today_pnl_cny,
                    "up_count": up_count,
                    "down_count": down_count,
                    "alert_count": sum(len(row["alerts"]) for row in rows),
                    "position_count": len(rows),
                    "weights_are_estimates": True,
                    "cash_not_included": True,
                },
                "positions": rows,
                "combined_exposure": build_combined_exposure(combined_rows),
            },
            warnings=list(dict.fromkeys(warnings)),
            errors=errors,
            sources=[{"name": "STJ SQLite"}, {"name": "腾讯财经 / Yahoo Finance"}],
        )

    def quote(self, ts_code: str) -> dict[str, Any]:
        code = normalize_ts_code(ts_code)
        try:
            data, cache_meta, warnings = self._quote(code)
            return envelope(
                data,
                market=market_group(code),
                as_of=data.get("quote_time") or data.get("bar_time"),
                cache=cache_meta,
                warnings=warnings,
                sources=[{"name": data.get("source"), "as_of": data.get("quote_time") or data.get("bar_time")}],
            )
        except Exception as exc:
            return envelope(
                {"asset": asset_ref(code), "last": None},
                ok=False,
                market=market_group(code),
                warnings=["行情未确认"],
                errors=[_provider_error("quote", exc)],
                status=502,
            )

    def watchlist(self, force_refresh: bool = False) -> dict[str, Any]:
        with self.connection() as conn:
            watches = get_watchlist(conn)
            notes_map = get_notes_map(conn, [row["ts_code"] for row in watches], limit=5)
        rows = []
        errors = []
        warnings: list[str] = []
        quote_map, quote_failures, quote_warnings = self._quotes_many(
            [row["ts_code"] for row in watches], force_refresh=force_refresh,
        )
        warnings.extend(quote_warnings)
        for watch in watches:
            code = watch["ts_code"]
            quote = quote_map.get(code)
            if quote is None:
                quote = {"asset": asset_ref(code, name=watch.get("name"), exchange=watch.get("exchange")), "last": None, "source": "未确认"}
                errors.append(_provider_error(f"watchlist.quote.{code}", quote_failures.get(code) or RuntimeError("行情不可用")))
            last = finite_number(quote.get("last"))
            target = finite_number(watch.get("target_price"))
            distance = (target - last) / last * 100 if target is not None and last else None
            rows.append({
                **watch,
                "asset": quote.get("asset") or asset_ref(code, name=watch.get("name")),
                "quote": quote,
                "distance_to_target_pct": distance,
                "recent_notes": notes_map.get(code, []),
            })
        market_counts = {group: sum(1 for row in rows if row["asset"]["market_group"] == group) for group in ("A", "HK", "US")}
        return envelope(
            {"summary": {"count": len(rows), "market_counts": market_counts}, "watchlist": rows},
            warnings=list(dict.fromkeys(warnings)),
            errors=errors,
            sources=[{"name": "STJ SQLite"}, {"name": "腾讯财经 / Yahoo Finance"}],
        )

    def stock_context(self, ts_code: str) -> dict[str, Any]:
        code = normalize_ts_code(ts_code)
        with self.connection() as conn:
            position = get_position(conn, code)
            watch = get_watch(conn, code)
            notes = get_notes(conn, code, limit=100)
            trades = get_trades_for_symbol(conn, code, limit=200)
        errors: list[dict[str, Any]] = []
        warnings: list[str] = []
        try:
            quote, _, quote_warnings = self._quote(code)
            warnings.extend(quote_warnings)
        except Exception as exc:
            quote = {"asset": asset_ref(code), "last": None, "source": "未确认"}
            errors.append(_provider_error("stock.quote", exc))
        try:
            profile, _, profile_warnings = self._cached(
                "yahoo", "profile", {"ts_code": code}, TTL["profile"], lambda: self.yahoo.profile(code)
            )
            warnings.extend(profile_warnings)
            warnings.extend(profile.get("warnings") or [])
        except Exception as exc:
            profile = {
                "asset": quote.get("asset") or asset_ref(code),
                "business_summary": None,
                "sector": None,
                "industry": None,
                "facts": [],
                "source": None,
            }
            errors.append(_provider_error("stock.profile", exc))
        try:
            valuation, _, valuation_warnings = self._cached(
                "yahoo", "valuation", {"ts_code": code}, TTL["valuation"], lambda: self.yahoo.valuation(code)
            )
            warnings.extend(valuation_warnings)
        except Exception as exc:
            valuation = {}
            errors.append(_provider_error("stock.valuation", exc))
        if market_group(code) == "A":
            current = quote.get("valuation") or {}
            valuation = {**valuation, **{key: value for key, value in current.items() if value is not None}}
            valuation.setdefault("source", "腾讯财经 / Yahoo Finance")
        quantity = finite_number(position.get("quantity")) if position else None
        avg_cost = finite_number(position.get("avg_cost")) if position else None
        last = finite_number(quote.get("last"))
        total_cost = finite_number(position.get("total_cost")) if position else None
        if total_cost is None and quantity is not None and avg_cost is not None:
            total_cost = quantity * avg_cost
        pnl = last * quantity - total_cost if last is not None and quantity is not None and total_cost is not None else None
        pnl_rate = pnl / total_cost * 100 if pnl is not None and total_cost else None
        return envelope(
            {
                "asset": profile.get("asset") or quote.get("asset") or asset_ref(code),
                "position": position,
                "watch": watch,
                "quote": quote,
                "holding_summary": {
                    "quantity": quantity,
                    "avg_cost": avg_cost,
                    "last": last,
                    "pnl": pnl,
                    "pnl_rate": pnl_rate,
                    "currency": (quote.get("asset") or {}).get("currency") or (position or {}).get("currency"),
                },
                "company_profile": profile,
                "valuation": valuation,
                "trades": trades,
                "notes": notes,
            },
            market=market_group(code),
            warnings=list(dict.fromkeys(warnings)),
            errors=errors,
            sources=[{"name": "STJ SQLite"}, {"name": quote.get("source")}, {"name": profile.get("source")}],
        )

    def financials(self, ts_code: str, period: str = "annual") -> dict[str, Any]:
        code = normalize_ts_code(ts_code)
        normalized_period = "quarterly" if period in {"q", "quarter", "quarterly"} else "annual"
        try:
            data, cache_meta, warnings = self._cached(
                "yahoo",
                "financials",
                {"ts_code": code, "period": normalized_period},
                TTL["financials"],
                lambda: self.yahoo.financials(code, normalized_period),
            )
            available = bool(data.get("series"))
            data["capability"] = {
                "available": available,
                "reason": None if available else "当前来源没有返回可用财务序列",
            }
            return envelope(
                data,
                market=market_group(code),
                as_of=data.get("as_of"),
                cache=cache_meta,
                warnings=warnings,
                sources=[{"name": data.get("source"), "as_of": data.get("as_of")}],
            )
        except Exception as exc:
            return envelope(
                {"asset": asset_ref(code), "period": normalized_period, "series": [], "capability": {"available": False, "reason": str(exc)}},
                market=market_group(code),
                warnings=["财务数据暂不可用"],
                errors=[_provider_error("stock.financials", exc)],
            )

    def flow(self, ts_code: str) -> dict[str, Any]:
        code = normalize_ts_code(ts_code)
        if market_group(code) != "A":
            return envelope(
                {
                    "capability": {"available": False, "reason": "港美股没有接入同口径、可核验的个股净资金流"},
                    "fund_flow": [],
                    "margin": [],
                },
                market=market_group(code),
                warnings=["此处不使用成交表现冒充个股资金流"],
            )
        try:
            data, cache_meta, warnings = self._cached(
                "eastmoney", "flow", {"ts_code": code}, TTL["flow"], lambda: self.a_stock.flow_bundle(code)
            )
            return envelope(
                data,
                market="A",
                as_of=data.get("as_of"),
                cache=cache_meta,
                warnings=warnings,
                sources=[{"name": "东方财富", "as_of": data.get("as_of")}],
            )
        except Exception as exc:
            return envelope(
                {"capability": {"available": False, "reason": str(exc)}, "fund_flow": [], "margin": []},
                market="A",
                warnings=["A 股资金面暂不可用"],
                errors=[_provider_error("stock.flow", exc)],
            )

    def options(self, ts_code: str) -> dict[str, Any]:
        code = normalize_ts_code(ts_code)
        try:
            data, cache_meta, warnings = self._cached(
                "yahoo", "options", {"ts_code": code}, TTL["options"], lambda: self.yahoo.options(code)
            )
            return envelope(
                data,
                market=market_group(code),
                cache=cache_meta,
                warnings=warnings,
                sources=[{"name": data.get("source"), "as_of": data.get("as_of")}],
            )
        except Exception as exc:
            return envelope(
                {"capability": {"available": False, "reason": str(exc)}, "expirations": [], "calls": [], "puts": []},
                market=market_group(code),
                warnings=["期权链暂不可用"],
                errors=[_provider_error("stock.options", exc)],
            )

    def stock_intel(self, ts_code: str, kind: str = "all", limit: int = 30) -> dict[str, Any]:
        code = normalize_ts_code(ts_code)
        requested = kind if kind in {"all", "news", "report", "filing"} else "all"
        items: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        warnings: list[str] = []
        if requested in {"all", "news"}:
            try:
                rows, _, row_warnings = self._cached(
                    "yahoo", "news", {"ts_code": code, "limit": min(limit, 15)}, TTL["news"], lambda: self.yahoo.news(code, min(limit, 15))
                )
                items.extend(rows)
                warnings.extend(row_warnings)
            except Exception as exc:
                errors.append(_provider_error("stock.intel.news", exc))
        if requested in {"all", "report"}:
            try:
                if market_group(code) == "A":
                    loader = lambda: self.a_stock.reports(code, min(limit, 15))
                    provider = "eastmoney"
                else:
                    loader = lambda: self.yahoo.analyst_updates(code, min(limit, 15))
                    provider = "yahoo"
                rows, _, row_warnings = self._cached(
                    provider, "reports", {"ts_code": code, "limit": min(limit, 15)}, TTL["reports"], loader
                )
                items.extend(rows)
                warnings.extend(row_warnings)
            except Exception as exc:
                errors.append(_provider_error("stock.intel.reports", exc))
        if requested in {"all", "filing"} and market_group(code) == "A":
            try:
                rows, _, row_warnings = self._cached(
                    "eastmoney", "filings", {"ts_code": code, "limit": min(limit, 15)}, TTL["filings"], lambda: self.a_stock.announcements(code, min(limit, 15))
                )
                items.extend(rows)
                warnings.extend(row_warnings)
            except Exception as exc:
                errors.append(_provider_error("stock.intel.filings", exc))
        items = _dedupe_intel(items)
        items.sort(key=lambda row: str(row.get("published_at") or ""), reverse=True)
        return envelope(
            {"asset": asset_ref(code), "items": items[:limit], "filters": ["all", "news", "report", "filing"]},
            market=market_group(code),
            warnings=list(dict.fromkeys(warnings)),
            errors=errors,
            sources=[{"name": "Yahoo Finance / 东方财富"}],
        )

    @staticmethod
    def _market_status(market: str) -> dict[str, Any]:
        zones = {"A": "Asia/Shanghai", "HK": "Asia/Hong_Kong", "US": "America/New_York"}
        zone = ZoneInfo(zones[market])
        now = datetime.now(zone)
        if now.weekday() >= 5:
            state = "closed"
        else:
            minutes = now.hour * 60 + now.minute
            if market == "US":
                state = "open" if 570 <= minutes < 960 else "pre" if minutes < 570 else "closed"
            else:
                state = "open" if (570 <= minutes < 690 or 780 <= minutes < 900) else "pre" if minutes < 570 else "closed"
        return {
            "state": state,
            "local_time": now.isoformat(),
            "timezone": zones[market],
            "holiday_calendar": False,
        }

    def daily_review(self, market: str = "A", force_refresh: bool = False) -> dict[str, Any]:
        normalized_market = str(market or "A").upper()
        if normalized_market not in {"A", "HK", "US"}:
            raise DashboardError("market 必须是 A/HK/US", code="INVALID_MARKET", status=400, scope="daily-review")
        errors: list[dict[str, Any]] = []
        warnings = ["交易状态按工作日和常规时段估算，尚未接入交易所节假日日历"]
        indices: list[dict[str, Any]] = []
        temperature: dict[str, Any] | None = None
        leaders: list[dict[str, Any]] = []

        def load_market_modules() -> dict[str, Any]:
            result: dict[str, Any] = {}
            if normalized_market == "A":
                try:
                    result["overview"] = self._cached(
                        "eastmoney", "industry-overview-v3", {"market": "A"}, TTL["rotation"], self.a_stock.industry_overview,
                        force_refresh=force_refresh,
                    )
                except Exception as exc:
                    result["rotation_error"] = exc
                try:
                    result["leaders"] = self._cached(
                        "eastmoney", "market-leaders-v1", {"market": "A", "limit": 6}, TTL["rotation"], self.a_stock.market_leaders,
                        force_refresh=force_refresh,
                    )
                except Exception as exc:
                    result["leaders_error"] = exc
            else:
                try:
                    result["rotation"] = self._cached(
                        "yahoo", "proxy-rotation", {"market": normalized_market}, TTL["rotation"], lambda: self.yahoo.proxy_rotation(normalized_market),
                        force_refresh=force_refresh,
                    )
                except Exception as exc:
                    result["rotation_error"] = exc
            return result

        with ThreadPoolExecutor(max_workers=4) as executor:
            global_future = executor.submit(
                lambda: self._cached(
                    "yahoo", "global-indices", {}, TTL["indices"], self.yahoo.global_indices,
                    force_refresh=force_refresh,
                )
            )
            a_index_future = executor.submit(
                lambda: self._cached(
                    "tencent", "a-indices", {}, TTL["indices"], self.a_stock.indices,
                    force_refresh=force_refresh,
                )
            )
            market_future = executor.submit(load_market_modules)
            activity_future = executor.submit(
                lambda: self._cached(
                    "legulegu",
                    "market-activity-v1",
                    {"market": "A"},
                    TTL["rotation"],
                    self.a_stock.market_activity,
                    force_refresh=force_refresh,
                )
            ) if normalized_market == "A" else None

            try:
                global_rows, _, row_warnings = global_future.result()
                indices.extend(global_rows)
                warnings.extend(row_warnings)
            except Exception as exc:
                errors.append(_provider_error("daily-review.indices.global", exc))
            try:
                a_rows, _, row_warnings = a_index_future.result()
                by_key = {row["key"]: row for row in indices}
                for row in a_rows:
                    by_key[row["key"]] = row
                indices = list(by_key.values())
                warnings.extend(row_warnings)
            except Exception as exc:
                errors.append(_provider_error("daily-review.indices.a", exc))

            try:
                market_result = market_future.result()
            except Exception as exc:
                market_result = {"rotation_error": exc}
            rotation = []
            cache_meta = {"hit": False, "stale": False, "age_seconds": 0}
            if normalized_market == "A" and market_result.get("overview"):
                overview, cache_meta, row_warnings = market_result["overview"]
                rotation = overview.get("rotation") or []
                warnings.extend(overview.get("warnings") or [])
                warnings.extend(row_warnings)
            elif normalized_market != "A" and market_result.get("rotation"):
                rotation, cache_meta, row_warnings = market_result["rotation"]
                warnings.extend(row_warnings)
                positive = sum(1 for row in rotation if (finite_number(row.get("metric_value")) or 0) > 0)
                negative = sum(1 for row in rotation if (finite_number(row.get("metric_value")) or 0) < 0)
                flat = sum(1 for row in rotation if finite_number(row.get("metric_value")) == 0)
                temperature = market_temperature(
                    positive,
                    negative,
                    flat,
                    basis="行业 ETF / 指数涨跌样本，不代表全市场涨跌家数",
                    proxy=True,
                    as_of=max((str(row.get("as_of") or "") for row in rotation), default=None),
                )
            if market_result.get("rotation_error"):
                errors.append(_provider_error("daily-review.rotation", market_result["rotation_error"]))
            if market_result.get("leaders"):
                leaders, _, leader_warnings = market_result["leaders"]
                warnings.extend(leader_warnings)
            if market_result.get("leaders_error"):
                errors.append(_provider_error("daily-review.leaders", market_result["leaders_error"]))

            if activity_future is not None:
                try:
                    activity, _, activity_warnings = activity_future.result()
                    warnings.extend(activity_warnings)
                    temperature = market_temperature(
                        activity.get("positive_count"),
                        activity.get("negative_count"),
                        activity.get("flat_count"),
                        basis="沪深市场上涨/下跌/平盘家数（乐咕乐股）",
                        as_of=activity.get("as_of"),
                    )
                except Exception as exc:
                    errors.append(_provider_error("daily-review.temperature", exc))
        if temperature is None:
            temperature = market_temperature(
                0, 0, basis="可靠涨跌家数暂不可用", proxy=normalized_market != "A",
            )
        return envelope(
            {
                "market": normalized_market,
                "market_status": self._market_status(normalized_market),
                "indices": indices,
                "temperature": temperature,
                "leaders": leaders,
                "leaders_label": "领涨公司" if normalized_market == "A" else "领涨公司暂未接入",
                "leaders_basis": "东方财富沪深 A 股涨幅榜 · 已排除上市初期与退市整理标的" if normalized_market == "A" else "当前仅 A 股提供公司级涨幅榜",
                "leaders_as_of": max((str(row.get("as_of") or "") for row in leaders), default=None) or None,
                "rotation": rotation,
                "rotation_label": "行业资金流 · 流入/流出两端" if normalized_market == "A" else "行业/ETF 表现代理",
                "rotation_metric_kind": "net_flow" if normalized_market == "A" else "performance_proxy",
            },
            market=normalized_market,
            cache=cache_meta,
            warnings=list(dict.fromkeys(warnings)),
            errors=errors,
            sources=[{"name": "腾讯财经 / Yahoo Finance / 东方财富 / 乐咕乐股"}],
        )

    def intel_radar(self, scope: str = "all", market: str = "all", kind: str = "all") -> dict[str, Any]:
        normalized_scope = scope if scope in {"all", "holding", "watch", "investment"} else "all"
        normalized_market = str(market or "all").upper()
        normalized_kind = kind if kind in {"all", "news", "report", "filing", "investment_news"} else "all"
        with self.connection() as conn:
            positions = get_positions(conn)
            watches = get_watchlist(conn)
        errors: list[dict[str, Any]] = []
        universe: list[tuple[str, str, float | None]] = []
        if normalized_scope in {"all", "holding"}:
            universe.extend((row["ts_code"], "holding", None) for row in positions)
        if normalized_scope in {"all", "watch"}:
            held = {row["ts_code"] for row in positions}
            universe.extend((row["ts_code"], "watch", finite_number(row.get("priority"))) for row in watches if row["ts_code"] not in held)
        if normalized_market in {"A", "HK", "US"}:
            universe = [item for item in universe if market_group(item[0]) == normalized_market]
        items: list[dict[str, Any]] = []
        requested_kind = normalized_kind if normalized_kind != "investment_news" else "all"
        selected_universe = universe[:12]

        def load_symbol_intel(code: str) -> dict[str, Any]:
            worker = DashboardService(self.workspace)
            return worker.stock_intel(code, requested_kind, limit=6)

        def load_investment_news() -> list[dict[str, Any]]:
            worker = DashboardService(self.workspace)
            rows, _, _ = worker._cached(
                "yahoo", "investment-news", {"query": "global markets investment"}, TTL["news"],
                lambda: worker.yahoo.search_news("global markets investment", limit=15, kind="investment_news"),
            )
            return rows

        wants_portfolio = normalized_scope in {"all", "holding"}
        wants_investment = normalized_scope in {"all", "investment"} and normalized_kind in {"all", "news", "investment_news"}
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(selected_universe) + int(wants_portfolio) + int(wants_investment)))) as executor:
            portfolio_future = executor.submit(self.portfolio) if wants_portfolio else None
            symbol_futures = [(entry, executor.submit(load_symbol_intel, entry[0])) for entry in selected_universe]
            investment_future = executor.submit(load_investment_news) if wants_investment else None

            holding_weights: dict[str, float | None] = {}
            if portfolio_future is not None:
                try:
                    portfolio_response = portfolio_future.result()
                    holding_weights = {
                        row["asset"]["ts_code"]: finite_number(row.get("weight"))
                        for row in (portfolio_response.get("data") or {}).get("positions") or []
                    }
                    errors.extend(portfolio_response.get("errors") or [])
                except Exception as exc:
                    errors.append(_provider_error("intel.portfolio", exc))

            for (code, origin, watch_priority), future in symbol_futures:
                try:
                    response = future.result()
                except Exception as exc:
                    errors.append(_provider_error(f"intel.symbol.{code}", exc))
                    continue
                for row in (response.get("data") or {}).get("items") or []:
                    row = dict(row)
                    row["scope"] = origin
                    row["relevance_score"] = intel_relevance_score(
                        scope=origin,
                        holding_weight=holding_weights.get(code),
                        watch_priority=watch_priority,
                        published_at=row.get("published_at"),
                        has_risk_tag=bool(row.get("risk_tags")),
                    )
                    items.append(row)
                errors.extend(response.get("errors") or [])

            if investment_future is not None:
                try:
                    for row in investment_future.result():
                        row = dict(row)
                        row["scope"] = "investment"
                        row["relevance_score"] = intel_relevance_score(
                            scope="investment",
                            published_at=row.get("published_at"),
                            has_risk_tag=bool(row.get("risk_tags")),
                        )
                        items.append(row)
                except Exception as exc:
                    errors.append(_provider_error("intel.investment-news", exc))
        items = _dedupe_intel(items)
        if normalized_kind != "all":
            items = [row for row in items if row.get("kind") == normalized_kind]
        items.sort(key=lambda row: (finite_number(row.get("relevance_score")) or 0, str(row.get("published_at") or "")), reverse=True)
        return envelope(
            {"items": items[:80], "universe_count": len(universe), "filters": {"scope": normalized_scope, "market": normalized_market, "kind": normalized_kind}},
            warnings=[] if items else ["当前筛选下没有可展示资讯"],
            errors=errors,
            sources=[{"name": "Yahoo Finance / 东方财富"}],
        )

    def sectors(self, include_archived: bool = False) -> dict[str, Any]:
        with self.connection() as conn:
            rows = list_sectors(conn, include_archived=include_archived)
        return envelope({"sectors": rows}, sources=[{"name": "STJ SQLite"}])

    def sector(self, sector_id: int) -> dict[str, Any]:
        with self.connection() as conn:
            row = get_sector(conn, sector_id)
        return envelope(row, sources=[{"name": "STJ SQLite"}])

    def mutate_sector(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            with self.connection() as conn:
                sector_id = int(payload.get("sector_id") or 0)
                if action == "create":
                    row = create_sector(conn, payload.get("name", ""), payload.get("summary", ""), payload.get("slug"))
                    for tag in payload.get("tags") or []:
                        add_sector_tag(conn, row["id"], str(tag))
                    row = get_sector(conn, row["id"])
                elif action == "update":
                    row = update_sector(conn, sector_id, **{key: payload[key] for key in ("name", "summary", "status") if key in payload})
                elif action == "archive":
                    row = archive_sector(conn, sector_id)
                elif action == "tag-add":
                    row = add_sector_tag(conn, sector_id, payload.get("name", ""))
                elif action == "tag-delete":
                    row = {"deleted": delete_sector_tag(conn, sector_id, int(payload.get("item_id") or 0))}
                elif action == "node-add":
                    row = add_sector_node(
                        conn, sector_id, payload.get("name", ""), payload.get("stage", "midstream"),
                        payload.get("description", ""), bool(payload.get("bottleneck")), int(payload.get("sort_order") or 0),
                    )
                elif action == "node-update":
                    row = update_sector_node(
                        conn, sector_id, int(payload.get("item_id") or 0),
                        **{key: payload[key] for key in ("name", "stage", "description", "bottleneck", "sort_order") if key in payload},
                    )
                elif action == "node-delete":
                    row = {"deleted": delete_sector_node(conn, sector_id, int(payload.get("item_id") or 0))}
                elif action == "edge-add":
                    row = add_sector_edge(
                        conn, sector_id, int(payload.get("from_node_id") or 0), int(payload.get("to_node_id") or 0),
                        payload.get("relation", "supplies"), int(payload.get("sort_order") or 0),
                    )
                elif action == "edge-delete":
                    row = {"deleted": delete_sector_edge(conn, sector_id, int(payload.get("item_id") or 0))}
                elif action == "symbol-add":
                    row = add_sector_symbol(conn, sector_id, normalize_ts_code(payload.get("ts_code", "")), payload.get("role", ""), payload.get("note", ""))
                elif action == "symbol-delete":
                    row = {"deleted": delete_sector_symbol(conn, sector_id, normalize_ts_code(payload.get("ts_code", "")))}
                elif action == "knowledge-add":
                    row = add_sector_knowledge(
                        conn, sector_id, payload.get("kind", "core"), payload.get("title", ""), payload.get("content", ""),
                        payload.get("source_url", ""), payload.get("as_of"),
                    )
                elif action == "knowledge-update":
                    row = update_sector_knowledge(
                        conn, sector_id, int(payload.get("item_id") or 0),
                        **{key: payload[key] for key in ("kind", "title", "content", "source_url", "as_of") if key in payload},
                    )
                elif action == "knowledge-delete":
                    row = {"deleted": delete_sector_knowledge(conn, sector_id, int(payload.get("item_id") or 0))}
                else:
                    raise DashboardError("未知板块操作", code="INVALID_ACTION", status=400, scope="sector")
            return envelope(row, sources=[{"name": "STJ SQLite"}])
        except DashboardError:
            raise
        except (TypeError, ValueError) as exc:
            raise DashboardError(str(exc), code="INVALID_INPUT", status=400, scope="sector") from exc

    def save_research_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        clean = _redact_sensitive(payload)
        try:
            with self.connection() as conn:
                row = add_research_record(
                    conn,
                    scope_type=clean.get("scope_type", "page"),
                    question=clean.get("question", ""),
                    answer=clean.get("answer", ""),
                    ts_code=clean.get("ts_code"),
                    sector_id=int(clean["sector_id"]) if clean.get("sector_id") is not None else None,
                    sources=clean.get("sources") or [],
                    context_summary=clean.get("context_summary") or {},
                    model_label=clean.get("model_label", ""),
                )
            return envelope(row, sources=[{"name": "STJ SQLite"}])
        except (TypeError, ValueError) as exc:
            raise DashboardError(str(exc), code="INVALID_INPUT", status=400, scope="research-record") from exc

    def research_records(self, **filters: Any) -> dict[str, Any]:
        with self.connection() as conn:
            rows = list_research_records(conn, **filters)
        return envelope({"records": rows}, sources=[{"name": "STJ SQLite"}])

    def delete_research_records(self, *, record_id: Any = None, clear_all: bool = False) -> dict[str, Any]:
        try:
            with self.connection() as conn:
                if clear_all:
                    deleted = clear_research_records(conn)
                    data = {"deleted": deleted, "all": True}
                else:
                    if record_id is None:
                        raise ValueError("record_id is required")
                    normalized_id = int(record_id)
                    if normalized_id <= 0:
                        raise ValueError("record_id must be positive")
                    deleted = delete_research_record(conn, normalized_id)
                    data = {"deleted": deleted, "record_id": normalized_id}
            return envelope(data, sources=[{"name": "STJ SQLite"}])
        except (TypeError, ValueError) as exc:
            raise DashboardError(str(exc), code="INVALID_INPUT", status=400, scope="research-record") from exc
