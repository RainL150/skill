"""Yahoo-backed cross-market profile, financial, news and options provider."""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote as urlquote

from db_schema import parse_ts_code
from quote_adapter import fetch_quote, fetch_quotes_many, quote_many, yahoo_symbol
from dashboard.contracts import asset_ref, finite_number, normalize_ts_code, utc_now
from dashboard.providers.base import ProviderError, request_json, session


YAHOO_SEARCH = "https://query1.finance.yahoo.com/v1/finance/search"
YAHOO_CRUMB = "https://query1.finance.yahoo.com/v1/test/getcrumb"
YAHOO_SUMMARY = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
YAHOO_TIMESERIES = "https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}"
YAHOO_OPTIONS = "https://query2.finance.yahoo.com/v7/finance/options/{symbol}"


FINANCIAL_FIELDS = {
    "TotalRevenue": "revenue",
    "NetIncome": "net_income",
    "FreeCashFlow": "free_cash_flow",
    "GrossProfit": "gross_profit",
    "OperatingCashFlow": "operating_cash_flow",
    "CapitalExpenditure": "capital_expenditure",
    "ResearchAndDevelopment": "r_and_d",
    "TotalAssets": "total_assets",
    "TotalLiabilitiesNetMinorityInterest": "total_liabilities",
    "CurrentAssets": "current_assets",
    "CurrentLiabilities": "current_liabilities",
    "AccountsReceivable": "receivables",
    "Inventory": "inventory",
    "DilutedEPS": "eps_actual",
}


def _raw(value: Any) -> float | int | None:
    if isinstance(value, dict):
        value = value.get("raw")
    return finite_number(value)


class YahooClient:
    provider = "yahoo"

    def __init__(self) -> None:
        self.client = session(trust_env=True)
        self.crumb: str | None = None

    def _ensure_crumb(self, force: bool = False) -> str:
        if self.crumb and not force:
            return self.crumb
        if force:
            self.crumb = None
            self.client.cookies.clear()
        try:
            self.client.get("https://fc.yahoo.com", timeout=(5, 12), allow_redirects=True)
            response = self.client.get(YAHOO_CRUMB, timeout=(5, 12))
            response.raise_for_status()
            crumb = response.text.strip()
        except Exception as exc:
            raise ProviderError("yahoo", "YAHOO_AUTH", f"Yahoo 会话初始化失败：{exc}", retryable=True) from exc
        if not crumb or "<" in crumb or len(crumb) > 200:
            raise ProviderError("yahoo", "YAHOO_AUTH", "Yahoo 返回了无效 crumb", retryable=True)
        self.crumb = crumb
        return crumb

    def summary(self, ts_code: str, modules: list[str]) -> dict[str, Any]:
        code = normalize_ts_code(ts_code)
        symbol = yahoo_symbol(code)
        for attempt in range(2):
            crumb = self._ensure_crumb(force=attempt > 0)
            try:
                payload = request_json(
                    "yahoo",
                    self.client,
                    YAHOO_SUMMARY.format(symbol=urlquote(symbol)),
                    params={"modules": ",".join(modules), "crumb": crumb},
                    retries=0,
                )
            except ProviderError as exc:
                if attempt == 0 and exc.code in {"UPSTREAM_HTTP", "UPSTREAM_FORBIDDEN"}:
                    continue
                raise
            error = (payload.get("quoteSummary") or {}).get("error")
            if error:
                if attempt == 0:
                    continue
                raise ProviderError("yahoo", "UPSTREAM_SCHEMA", str(error))
            result = ((payload.get("quoteSummary") or {}).get("result") or [None])[0]
            if result:
                return result
        raise ProviderError("yahoo", "UPSTREAM_EMPTY", f"Yahoo 没有返回 {symbol} 数据")

    def search(self, query: str, *, quotes_count: int = 1, news_count: int = 10) -> dict[str, Any]:
        return request_json(
            "yahoo",
            self.client,
            YAHOO_SEARCH,
            params={
                "q": query,
                "quotesCount": min(max(quotes_count, 0), 10),
                "newsCount": min(max(news_count, 0), 30),
            },
            retries=1,
        )

    @staticmethod
    def _normalize_quote(code: str, raw: dict[str, Any], *, fx_as_of: str | None = None) -> dict[str, Any]:
        if not raw.get("ok"):
            raise ProviderError("yahoo", "QUOTE_UNAVAILABLE", str(raw.get("error") or "行情不可用"), retryable=True)
        price = finite_number(raw.get("price"))
        previous = finite_number(raw.get("previous_close"))
        change = price - previous if price is not None and previous is not None else None
        change_pct = change / previous * 100 if change is not None and previous else None
        return {
            "asset": asset_ref(
                code,
                name=raw.get("name"),
                exchange=raw.get("exchange"),
                currency=raw.get("currency"),
            ),
            "last": price,
            "previous_close": previous,
            "change": change,
            "change_pct": change_pct,
            "quote_time": raw.get("regular_market_time") or raw.get("bar_time"),
            "bar_time": raw.get("bar_time"),
            "source": raw.get("source") or "Yahoo Finance",
            "source_url": raw.get("source_url"),
            "delayed": True,
            "stale": False,
            "cny_rate": finite_number(raw.get("cny_rate")),
            "cny_rate_source": raw.get("cny_rate_source"),
            "fx_as_of": fx_as_of,
        }

    def quote(self, ts_code: str) -> dict[str, Any]:
        code = normalize_ts_code(ts_code)
        return self._normalize_quote(code, fetch_quote(code))

    def quotes(self, ts_codes: list[str]) -> dict[str, dict[str, Any]]:
        """Fetch cross-market portfolio quotes concurrently and resolve FX once."""
        codes = list(dict.fromkeys(normalize_ts_code(code) for code in ts_codes))
        if not codes:
            return {}
        payload = quote_many(codes)
        raw_quotes = payload.get("quotes") or {}
        fx_rates = payload.get("fx_rates") or {}
        output: dict[str, dict[str, Any]] = {}
        for code in codes:
            raw = raw_quotes.get(code) or {}
            if not raw.get("ok"):
                continue
            currency = str(raw.get("currency") or "").upper()
            output[code] = self._normalize_quote(
                code,
                raw,
                fx_as_of=(fx_rates.get(currency) or {}).get("quote_time"),
            )
        return output

    def profile(self, ts_code: str) -> dict[str, Any]:
        code = normalize_ts_code(ts_code)
        symbol = yahoo_symbol(code)
        search_payload = self.search(symbol, quotes_count=3, news_count=0)
        candidates = search_payload.get("quotes") or []
        matched = next((row for row in candidates if str(row.get("symbol", "")).upper() == symbol.upper()), candidates[0] if candidates else {})
        warnings: list[str] = []
        try:
            summary = self.summary(code, ["assetProfile"])
            profile = summary.get("assetProfile") or {}
        except Exception as exc:
            profile = {}
            warnings.append(f"公司详细资料暂不可用：{exc}")
        return {
            "asset": asset_ref(
                code,
                name=matched.get("longname") or matched.get("shortname") or code,
                exchange=matched.get("exchDisp"),
            ),
            "business_summary": profile.get("longBusinessSummary"),
            "sector": profile.get("sector") or matched.get("sectorDisp") or matched.get("sector"),
            "industry": profile.get("industry") or matched.get("industryDisp") or matched.get("industry"),
            "website": profile.get("website"),
            "country": profile.get("country"),
            "employees": finite_number(profile.get("fullTimeEmployees")),
            "facts": [
                {"label": "行业", "value": profile.get("industry") or matched.get("industryDisp")},
                {"label": "板块", "value": profile.get("sector") or matched.get("sectorDisp")},
                {"label": "地区", "value": profile.get("country")},
                {"label": "员工", "value": finite_number(profile.get("fullTimeEmployees"))},
            ],
            "source": "Yahoo Finance company profile",
            "source_url": f"https://finance.yahoo.com/quote/{urlquote(symbol)}/profile",
            "as_of": utc_now(),
            "warnings": warnings,
        }

    def valuation(self, ts_code: str) -> dict[str, Any]:
        code = normalize_ts_code(ts_code)
        summary = self.summary(code, ["summaryDetail", "defaultKeyStatistics", "financialData"])
        detail = summary.get("summaryDetail") or {}
        stats = summary.get("defaultKeyStatistics") or {}
        financial = summary.get("financialData") or {}
        return {
            "pe_ttm": _raw(detail.get("trailingPE")),
            "pe_forward": _raw(detail.get("forwardPE")),
            "pb": _raw(stats.get("priceToBook")),
            "ps_ttm": _raw(detail.get("priceToSalesTrailing12Months")),
            "enterprise_to_ebitda": _raw(stats.get("enterpriseToEbitda")),
            "market_cap": _raw(detail.get("marketCap")),
            "enterprise_value": _raw(stats.get("enterpriseValue")),
            "beta": _raw(stats.get("beta")),
            "target_mean_price": _raw(financial.get("targetMeanPrice")),
            "recommendation_key": financial.get("recommendationKey"),
            "analyst_count": _raw(financial.get("numberOfAnalystOpinions")),
            "historical_percentile": None,
            "source": "Yahoo Finance quote summary",
            "as_of": utc_now(),
        }

    def financials(self, ts_code: str, period: str = "annual") -> dict[str, Any]:
        code = normalize_ts_code(ts_code)
        symbol = yahoo_symbol(code)
        prefix = "quarterly" if period == "quarterly" else "annual"
        types = [f"{prefix}{field}" for field in FINANCIAL_FIELDS]
        now = int(time.time())
        payload = request_json(
            "yahoo",
            self.client,
            YAHOO_TIMESERIES.format(symbol=urlquote(symbol)),
            params={
                "symbol": symbol,
                "type": ",".join(types),
                "period1": now - 12 * 366 * 24 * 3600,
                "period2": now + 366 * 24 * 3600,
            },
            retries=1,
        )
        error = (payload.get("timeseries") or {}).get("error")
        if error:
            raise ProviderError("yahoo", "UPSTREAM_SCHEMA", str(error))
        rows: dict[str, dict[str, Any]] = {}
        for series in (payload.get("timeseries") or {}).get("result") or []:
            type_names = (series.get("meta") or {}).get("type") or []
            type_name = str(type_names[0] if type_names else "")
            if not type_name.startswith(prefix):
                continue
            field_name = type_name[len(prefix):]
            target = FINANCIAL_FIELDS.get(field_name)
            if not target:
                continue
            for item in series.get(type_name) or []:
                date = str(item.get("asOfDate") or "")[:10]
                if not date:
                    continue
                row = rows.setdefault(date, {
                    "period_end": date,
                    "period_type": "Q" if prefix == "quarterly" else "FY",
                    "fiscal_year": int(date[:4]) if date[:4].isdigit() else None,
                    "currency": item.get("currencyCode"),
                    "source": "Yahoo Finance fundamentals timeseries",
                    "filed_at": None,
                })
                if not row.get("currency"):
                    row["currency"] = item.get("currencyCode")
                row[target] = _raw(item.get("reportedValue"))
        output = []
        for date in sorted(rows):
            row = rows[date]
            revenue = finite_number(row.get("revenue"))
            gross_profit = finite_number(row.get("gross_profit"))
            net_income = finite_number(row.get("net_income"))
            operating_cf = finite_number(row.get("operating_cash_flow"))
            assets = finite_number(row.get("total_assets"))
            liabilities = finite_number(row.get("total_liabilities"))
            current_assets = finite_number(row.get("current_assets"))
            current_liabilities = finite_number(row.get("current_liabilities"))
            row["gross_margin"] = gross_profit / revenue * 100 if gross_profit is not None and revenue else None
            row["operating_cash_ratio"] = operating_cf / net_income if operating_cf is not None and net_income else None
            row["debt_ratio"] = liabilities / assets * 100 if liabilities is not None and assets else None
            row["working_capital"] = current_assets - current_liabilities if current_assets is not None and current_liabilities is not None else None
            if row.get("free_cash_flow") is None and operating_cf is not None:
                capex = finite_number(row.get("capital_expenditure"))
                if capex is not None:
                    row["free_cash_flow"] = operating_cf + capex if capex < 0 else operating_cf - capex
                    row["free_cash_flow_formula"] = "operating_cash_flow +/- capital_expenditure"
            output.append(row)
        return {
            "asset": asset_ref(code),
            "period": period,
            "series": output[-8:],
            "source": "Yahoo Finance fundamentals timeseries",
            "as_of": output[-1]["period_end"] if output else utc_now(),
        }

    def news(self, ts_code: str, limit: int = 15) -> list[dict[str, Any]]:
        code = normalize_ts_code(ts_code)
        symbol = yahoo_symbol(code)
        return self.search_news(symbol, limit=limit, kind="news", related_assets=[code])

    def search_news(
        self,
        query: str,
        *,
        limit: int = 15,
        kind: str = "investment_news",
        related_assets: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        payload = self.search(query, quotes_count=1, news_count=limit)
        fetched_at = utc_now()
        output = []
        for row in (payload.get("news") or [])[:limit]:
            title = str(row.get("title") or "").strip()
            if not title:
                continue
            published_epoch = finite_number(row.get("providerPublishTime"))
            published = datetime.fromtimestamp(published_epoch, timezone.utc).isoformat() if published_epoch else None
            link = str(row.get("link") or "")
            output.append({
                "id": str(row.get("uuid") or hashlib.sha256(f"{title}{link}".encode()).hexdigest()[:20]),
                "kind": kind,
                "title": title,
                "summary": None,
                "related_assets": related_assets or [],
                "source_name": str(row.get("publisher") or "Yahoo Finance"),
                "source_url": link,
                "published_at": published,
                "fetched_at": fetched_at,
                "risk_tags": [],
            })
        return output

    def analyst_updates(self, ts_code: str, limit: int = 15) -> list[dict[str, Any]]:
        code = normalize_ts_code(ts_code)
        try:
            summary = self.summary(code, ["upgradeDowngradeHistory"])
        except Exception:
            return []
        history = (summary.get("upgradeDowngradeHistory") or {}).get("history") or []
        fetched_at = utc_now()
        output = []
        for item in history[:limit]:
            epoch = finite_number(item.get("epochGradeDate"))
            published = datetime.fromtimestamp(epoch, timezone.utc).isoformat() if epoch else None
            firm = str(item.get("firm") or "机构")
            action = str(item.get("action") or "更新")
            to_grade = str(item.get("toGrade") or "")
            title = f"{firm} {action} {to_grade}".strip()
            output.append({
                "id": hashlib.sha256(f"{code}{title}{published}".encode()).hexdigest()[:20],
                "kind": "report",
                "title": title,
                "summary": f"评级由 {item.get('fromGrade') or '—'} 调整为 {to_grade or '—'}",
                "related_assets": [code],
                "source_name": firm,
                "source_url": f"https://finance.yahoo.com/quote/{urlquote(yahoo_symbol(code))}/analysis",
                "published_at": published,
                "fetched_at": fetched_at,
                "risk_tags": [],
            })
        return output

    def options(self, ts_code: str) -> dict[str, Any]:
        code = normalize_ts_code(ts_code)
        _, market, _ = parse_ts_code(code)
        if market != "US":
            return {
                "capability": {"available": False, "reason": "首版期权链仅支持美股标的"},
                "expirations": [],
                "calls": [],
                "puts": [],
            }
        symbol = yahoo_symbol(code)
        crumb = self._ensure_crumb()
        payload = request_json(
            "yahoo",
            self.client,
            YAHOO_OPTIONS.format(symbol=urlquote(symbol)),
            params={"crumb": crumb},
            retries=1,
        )
        result = ((payload.get("optionChain") or {}).get("result") or [None])[0]
        if not result:
            return {
                "capability": {"available": False, "reason": "该标的没有可用期权链"},
                "expirations": [],
                "calls": [],
                "puts": [],
            }
        option = (result.get("options") or [{}])[0]
        normalize_contract = lambda row: {
            "contract": row.get("contractSymbol"),
            "strike": finite_number(row.get("strike")),
            "last": finite_number(row.get("lastPrice")),
            "bid": finite_number(row.get("bid")),
            "ask": finite_number(row.get("ask")),
            "volume": finite_number(row.get("volume")),
            "open_interest": finite_number(row.get("openInterest")),
            "implied_volatility": finite_number(row.get("impliedVolatility")),
            "in_the_money": bool(row.get("inTheMoney")),
        }
        return {
            "capability": {"available": True, "reason": None},
            "underlying_price": finite_number((result.get("quote") or {}).get("regularMarketPrice")),
            "expirations": result.get("expirationDates") or [],
            "calls": [normalize_contract(row) for row in (option.get("calls") or [])[:40]],
            "puts": [normalize_contract(row) for row in (option.get("puts") or [])[:40]],
            "source": "Yahoo Finance options",
            "as_of": utc_now(),
        }

    def proxy_rotation(self, market: str) -> list[dict[str, Any]]:
        definitions = {
            "US": [
                ("科技", "XLK"), ("金融", "XLF"), ("能源", "XLE"), ("医疗", "XLV"),
                ("可选消费", "XLY"), ("工业", "XLI"), ("必选消费", "XLP"),
                ("公用事业", "XLU"), ("地产", "XLRE"), ("材料", "XLB"),
            ],
            "HK": [
                ("恒生科技", "3032.HK"), ("香港大盘", "2800.HK"),
                ("中国企业", "2828.HK"), ("高股息", "3110.HK"),
            ],
        }
        if market not in definitions:
            return []
        rows = []
        codes = [f"{symbol}.US" if market == "US" else symbol for _, symbol in definitions[market]]
        snapshot = fetch_quotes_many(codes)
        for (name, symbol), ts_code in zip(definitions[market], codes):
            raw = snapshot.get(ts_code) or {}
            if not raw.get("ok"):
                continue
            price = finite_number(raw.get("price"))
            previous = finite_number(raw.get("previous_close"))
            change = price - previous if price is not None and previous is not None else None
            rows.append({
                "market": market,
                "sector_name": name,
                "metric_kind": "performance_proxy",
                "metric_value": change / previous * 100 if change is not None and previous else None,
                "metric_unit": "%",
                "rank": 0,
                "period": "session",
                "as_of": raw.get("regular_market_time") or raw.get("bar_time"),
                "source": f"Yahoo Finance ETF proxy · {symbol}",
                "proxy_symbol": symbol,
            })
        rows.sort(key=lambda row: row.get("metric_value") if row.get("metric_value") is not None else float("-inf"), reverse=True)
        for rank, row in enumerate(rows, 1):
            row["rank"] = rank
        return rows

    def global_indices(self) -> list[dict[str, Any]]:
        definitions = [
            ("上证指数", "000001.SH", "A"),
            ("创业板指", "399006.SZ", "A"),
            ("恒生指数", "^HSI.US", "HK"),
            ("恒生科技", "^HSTECH.US", "HK"),
            ("标普500", "^GSPC.US", "US"),
            ("纳斯达克", "^IXIC.US", "US"),
        ]
        rows = []
        raw_codes = [code[:-3] if code.endswith(".US") and code.startswith("^") else code for _, code, _ in definitions]
        snapshot = fetch_quotes_many(raw_codes)
        for (name, _, market), raw_code in zip(definitions, raw_codes):
            raw = snapshot.get(raw_code) or {}
            if not raw.get("ok"):
                continue
            price = finite_number(raw.get("price"))
            previous = finite_number(raw.get("previous_close"))
            change = price - previous if price is not None and previous is not None else None
            rows.append({
                "key": raw_code,
                "name": name,
                "market": market,
                "price": price,
                "change": change,
                "change_pct": change / previous * 100 if change is not None and previous else None,
                "as_of": raw.get("regular_market_time") or raw.get("bar_time"),
                "source": "Yahoo Finance",
            })
        return rows
