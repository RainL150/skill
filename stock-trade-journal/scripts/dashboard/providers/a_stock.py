"""A-share public-data provider with one Eastmoney rate gate."""

from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from db_schema import parse_ts_code
from dashboard.cache import CrossProcessRateGate
from dashboard.contracts import asset_ref, finite_number, normalize_ts_code, utc_now
from dashboard.providers.base import ProviderError, request_json, request_text, session


TENCENT_URL = "https://qt.gtimg.cn/q="
REPORT_URL = "https://reportapi.eastmoney.com/report/list"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
EASTMONEY_HEADERS = {
    "Referer": "https://quote.eastmoney.com/",
    "Origin": "https://quote.eastmoney.com",
}


class AStockProvider:
    provider = "a-stock"

    def __init__(self, cache_root: str | Path) -> None:
        self.tencent = session()
        self.public = session()
        self.eastmoney_direct = session(trust_env=False)
        self.eastmoney_proxy = session(trust_env=True)
        self._eastmoney_mode = "auto"
        self.rate_gate = CrossProcessRateGate(cache_root, "eastmoney", 1.0, (0.1, 0.5))

    @staticmethod
    def _prefix(code: str) -> str:
        return "sh" if code.startswith(("6", "9")) else "bj" if code.startswith("8") else "sz"

    @staticmethod
    def _num(values: list[str], index: int) -> float | int | None:
        try:
            return finite_number(values[index])
        except IndexError:
            return None

    def _parse_tencent(self, payload: str) -> dict[str, dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for line in payload.strip().split(";"):
            if "=" not in line or '"' not in line:
                continue
            key = line.split("=", 1)[0].rsplit("_", 1)[-1]
            values = line.split('"', 2)[1].split("~")
            if len(values) < 49:
                continue
            code = key[2:]
            rows[code] = {
                "name": values[1] or code,
                "price": self._num(values, 3),
                "previous_close": self._num(values, 4),
                "open": self._num(values, 5),
                "change": self._num(values, 31),
                "change_pct": self._num(values, 32),
                "high": self._num(values, 33),
                "low": self._num(values, 34),
                "amount_cny": self._num(values, 37) * 10_000 if self._num(values, 37) is not None else None,
                "turnover_pct": self._num(values, 38),
                "pe_ttm": self._num(values, 39),
                "market_cap_cny": self._num(values, 44) * 100_000_000 if self._num(values, 44) is not None else None,
                "pb": self._num(values, 46),
                "limit_up": self._num(values, 47),
                "limit_down": self._num(values, 48),
                "quote_time": values[30] if len(values) > 30 and values[30] else None,
            }
        return rows

    def quotes(self, ts_codes: list[str]) -> dict[str, dict[str, Any]]:
        normalized = [normalize_ts_code(code) for code in ts_codes]
        a_codes = [parse_ts_code(code)[0] for code in normalized if parse_ts_code(code)[1] in {"SH", "SZ"}]
        if not a_codes:
            return {}
        prefixed = [f"{self._prefix(code)}{code}" for code in a_codes]
        payload = request_text(
            "tencent",
            self.tencent,
            TENCENT_URL + ",".join(prefixed),
            encoding="gbk",
            timeout=(4.0, 10.0),
        )
        parsed = self._parse_tencent(payload)
        output: dict[str, dict[str, Any]] = {}
        for ts_code in normalized:
            symbol, market, exchange = parse_ts_code(ts_code)
            if market not in {"SH", "SZ"}:
                continue
            row = parsed.get(symbol)
            if not row:
                continue
            output[ts_code] = {
                "asset": asset_ref(ts_code, name=row.get("name"), exchange=exchange, currency="CNY"),
                "last": row.get("price"),
                "previous_close": row.get("previous_close"),
                "change": row.get("change"),
                "change_pct": row.get("change_pct"),
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "quote_time": row.get("quote_time"),
                "source": "腾讯财经",
                "source_url": f"https://gu.qq.com/{self._prefix(symbol)}{symbol}",
                "delayed": False,
                "stale": False,
                "valuation": {
                    "pe_ttm": row.get("pe_ttm"),
                    "pb": row.get("pb"),
                    "market_cap": row.get("market_cap_cny"),
                    "turnover_pct": row.get("turnover_pct"),
                },
            }
        return output

    def indices(self) -> list[dict[str, Any]]:
        mapping = {
            "000001": ("上证指数", "SH"),
            "399001": ("深证成指", "SZ"),
            "399006": ("创业板指", "SZ"),
            "000300": ("沪深300", "SH"),
        }
        # 000001 is ambiguous: ``sz000001`` is Ping An Bank, while the index is
        # ``sh000001``. Use the declared exchange instead of the stock-code heuristic.
        prefixed = [f"{market.lower()}{code}" for code, (_, market) in mapping.items()]
        payload = request_text("tencent", self.tencent, TENCENT_URL + ",".join(prefixed), encoding="gbk")
        parsed = self._parse_tencent(payload)
        return [
            {
                "key": f"{code}.{market}",
                "name": parsed.get(code, {}).get("name") or name,
                "market": "A",
                "price": parsed.get(code, {}).get("price"),
                "change": parsed.get(code, {}).get("change"),
                "change_pct": parsed.get(code, {}).get("change_pct"),
                "as_of": parsed.get(code, {}).get("quote_time"),
                "source": "腾讯财经",
            }
            for code, (name, market) in mapping.items()
            if parsed.get(code)
        ]

    def _eastmoney_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        retries: int = 1,
    ) -> Any:
        self.rate_gate.wait()
        merged_headers = {**EASTMONEY_HEADERS, **(headers or {})}
        clients = []
        if self._eastmoney_mode == "direct":
            clients = [("direct", self.eastmoney_direct)]
        elif self._eastmoney_mode == "proxy":
            clients = [("proxy", self.eastmoney_proxy)]
        else:
            clients = [("direct", self.eastmoney_direct), ("proxy", self.eastmoney_proxy)]
        last: Exception | None = None
        for mode, client in clients:
            try:
                payload = request_json(
                    "eastmoney",
                    client,
                    url,
                    params=params,
                    headers=merged_headers,
                    timeout=(5.0, 15.0),
                    retries=retries if mode == "proxy" else 0,
                )
                self._eastmoney_mode = mode
                return payload
            except ProviderError as exc:
                last = exc
                if exc.code == "UPSTREAM_FORBIDDEN":
                    break
        raise last or ProviderError("eastmoney", "UPSTREAM_UNKNOWN", "东财请求失败")

    def _eastmoney_clist(self, params: dict[str, Any], *, error_message: str) -> list[dict[str, Any]]:
        """Fetch one Eastmoney quote-list response with the shared host fallback."""
        last_error: ProviderError | None = None
        for host in ("push2.eastmoney.com", "push2delay.eastmoney.com"):
            try:
                payload = self._eastmoney_json(f"https://{host}/api/qt/clist/get", params=params)
                diff = (payload.get("data") or {}).get("diff") or []
                return list(diff.values()) if isinstance(diff, dict) else list(diff)
            except ProviderError as exc:
                last_error = exc
        raise last_error or ProviderError("eastmoney", "UPSTREAM_NETWORK", error_message, retryable=True)

    def reports(self, ts_code: str, limit: int = 15) -> list[dict[str, Any]]:
        code, market, _ = parse_ts_code(normalize_ts_code(ts_code))
        if market not in {"SH", "SZ"}:
            return []
        payload = self._eastmoney_json(
            REPORT_URL,
            params={
                "industryCode": "*",
                "pageSize": str(min(max(limit, 1), 50)),
                "industry": "*",
                "rating": "*",
                "ratingChange": "*",
                "beginTime": "2000-01-01",
                "endTime": "2030-01-01",
                "pageNo": "1",
                "qType": "0",
                "code": code,
            },
        )
        rows = payload.get("data") or []
        fetched_at = utc_now()
        output = []
        for row in rows[:limit]:
            info_code = str(row.get("infoCode") or row.get("info_code") or "")
            url = f"https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf" if info_code else ""
            title = str(row.get("title") or "").strip()
            if not title:
                continue
            published = str(row.get("publishDate") or row.get("publish_date") or "")[:19]
            output.append({
                "id": info_code or hashlib.sha256(f"{title}{published}".encode()).hexdigest()[:20],
                "kind": "report",
                "title": title,
                "summary": row.get("predictThisYearEps") and f"本年 EPS 预测 {row.get('predictThisYearEps')}",
                "related_assets": [ts_code],
                "source_name": str(row.get("orgSName") or "东方财富研报中心"),
                "source_url": url,
                "published_at": published or None,
                "fetched_at": fetched_at,
                "rating": row.get("emRatingName"),
                "risk_tags": [],
            })
        return output

    def announcements(self, ts_code: str, limit: int = 15) -> list[dict[str, Any]]:
        code, market, _ = parse_ts_code(normalize_ts_code(ts_code))
        if market not in {"SH", "SZ"}:
            return []
        payload = self._eastmoney_json(
            "https://np-anotice-stock.eastmoney.com/api/security/ann",
            params={
                "sr": -1,
                "page_size": min(max(limit, 1), 30),
                "page_index": 1,
                "ann_type": "A",
                "client_source": "web",
                "stock_list": code,
                "f_node": 0,
                "s_node": 0,
            },
        )
        rows = (payload.get("data") or {}).get("list") or []
        fetched_at = utc_now()
        output = []
        for row in rows[:limit]:
            title = str(row.get("title") or "").strip()
            if not title:
                continue
            art_code = str(row.get("art_code") or "")
            columns = [item.get("column_name") for item in row.get("columns") or [] if item.get("column_name")]
            published = str(row.get("notice_date") or "")[:19]
            output.append({
                "id": art_code or hashlib.sha256(f"{title}{published}".encode()).hexdigest()[:20],
                "kind": "filing",
                "title": title,
                "summary": columns[0] if columns else None,
                "related_assets": [ts_code],
                "source_name": "东方财富公告",
                "source_url": f"https://data.eastmoney.com/notices/detail/{code}/{art_code}.html" if art_code else "",
                "published_at": published or None,
                "fetched_at": fetched_at,
                "risk_tags": [],
            })
        return output

    def datacenter(
        self,
        report_name: str,
        *,
        filter_str: str = "",
        page_size: int = 30,
        sort_columns: str = "",
        sort_types: str = "-1",
    ) -> list[dict[str, Any]]:
        payload = self._eastmoney_json(
            DATACENTER_URL,
            params={
                "reportName": report_name,
                "columns": "ALL",
                "filter": filter_str,
                "pageNumber": "1",
                "pageSize": str(page_size),
                "sortColumns": sort_columns,
                "sortTypes": sort_types,
                "source": "WEB",
                "client": "WEB",
            },
        )
        return ((payload.get("result") or {}).get("data") or [])

    def fund_flow(self, ts_code: str, limit: int = 30) -> list[dict[str, Any]]:
        code, market, _ = parse_ts_code(normalize_ts_code(ts_code))
        if market not in {"SH", "SZ"}:
            return []
        secid = f"{1 if market == 'SH' else 0}.{code}"
        payload = self._eastmoney_json(
            "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
            params={
                "secid": secid,
                "fields1": "f1,f2,f3,f7",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
                "lmt": str(min(max(limit, 1), 120)),
            },
        )
        output = []
        for line in ((payload.get("data") or {}).get("klines") or []):
            parts = str(line).split(",")
            if len(parts) < 6:
                continue
            output.append({
                "date": parts[0],
                "main_net": finite_number(parts[1]),
                "small_net": finite_number(parts[2]),
                "mid_net": finite_number(parts[3]),
                "large_net": finite_number(parts[4]),
                "super_net": finite_number(parts[5]),
            })
        return output

    def margin_trading(self, ts_code: str, limit: int = 10) -> list[dict[str, Any]]:
        code, market, _ = parse_ts_code(normalize_ts_code(ts_code))
        if market not in {"SH", "SZ"}:
            return []
        rows = self.datacenter(
            "RPTA_WEB_RZRQ_GGMX",
            filter_str=f'(SCODE="{code}")',
            page_size=min(max(limit, 1), 30),
            sort_columns="DATE",
        )
        return [{
            "date": str(row.get("DATE") or "")[:10],
            "financing_balance": finite_number(row.get("RZYE")),
            "financing_buy": finite_number(row.get("RZMRE")),
            "securities_balance": finite_number(row.get("RQYE")),
            "total_balance": finite_number(row.get("RZRQYE")),
        } for row in rows]

    def flow_bundle(self, ts_code: str) -> dict[str, Any]:
        code = normalize_ts_code(ts_code)
        if parse_ts_code(code)[1] not in {"SH", "SZ"}:
            return {
                "capability": {"available": False, "reason": "当前只对 A 股提供可核验的个股资金流"},
                "fund_flow": [],
                "margin": [],
                "source": None,
            }
        return {
            "capability": {"available": True, "reason": None},
            "fund_flow": self.fund_flow(code),
            "margin": self.margin_trading(code),
            "source": "东方财富",
            "as_of": utc_now(),
        }

    def market_activity(self) -> dict[str, Any]:
        """A-share advance/decline breadth from Legu's public market-activity page."""
        payload = request_text(
            "legulegu",
            self.public,
            "https://legulegu.com/stockdata/market-activity",
            timeout=(5.0, 15.0),
        )

        def count(label: str) -> int | None:
            match = re.search(rf"<td>\s*{re.escape(label)}\s*</td>\s*<td[^>]*>\s*([\d,]+)\s*</td>", payload)
            return int(match.group(1).replace(",", "")) if match else None

        date_match = re.search(r'class="market-activity-time"[^>]*>\s*([^<]+)', payload)
        result = {
            "positive_count": count("上涨"),
            "negative_count": count("下跌"),
            "flat_count": count("平盘"),
            "limit_up_count": count("涨停"),
            "limit_down_count": count("跌停"),
            "as_of": date_match.group(1).strip() if date_match else None,
            "source": "乐咕乐股赚钱效应",
            "source_url": "https://legulegu.com/stockdata/market-activity",
        }
        if result["positive_count"] is None or result["negative_count"] is None:
            raise ProviderError("legulegu", "UPSTREAM_SCHEMA", "市场涨跌家数解析失败", retryable=True)
        return result

    def market_leaders(self, limit: int = 6) -> list[dict[str, Any]]:
        """Top advancing Shanghai/Shenzhen companies, excluding listing-day distortions."""
        row_limit = min(max(int(limit), 1), 10)
        rows = self._eastmoney_clist(
            {
                "pn": 1,
                "pz": max(30, row_limit * 4),
                "po": 1,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fid": "f3",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                "fields": "f12,f13,f14,f2,f3,f8,f100,f124",
            },
            error_message="A 股领涨公司不可用",
        )
        output: list[dict[str, Any]] = []
        for row in rows:
            code = str(row.get("f12") or "").strip()
            name = str(row.get("f14") or "").strip()
            change_pct = finite_number(row.get("f3"))
            if not re.fullmatch(r"\d{6}", code) or not name or change_pct is None or change_pct <= 0:
                continue
            if re.match(r"^(?:N|C|\*?ST)", name, re.IGNORECASE) or "退" in name:
                continue
            market = "SH" if str(row.get("f13")) == "1" else "SZ"
            timestamp = finite_number(row.get("f124"))
            try:
                as_of = datetime.fromtimestamp(float(timestamp), timezone.utc).isoformat() if timestamp else None
            except (OverflowError, OSError, ValueError):
                as_of = None
            output.append({
                "asset": asset_ref(f"{code}.{market}", name=name, currency="CNY"),
                "price": finite_number(row.get("f2")),
                "change_pct": change_pct,
                "turnover_pct": finite_number(row.get("f8")),
                "industry": str(row.get("f100") or "").strip() or None,
                "as_of": as_of,
                "source": "东方财富 A 股涨幅榜",
                "source_url": f"https://quote.eastmoney.com/{market.lower()}{code}.html",
            })
            if len(output) >= row_limit:
                break
        if not output:
            raise ProviderError("eastmoney", "UPSTREAM_SCHEMA", "A 股领涨公司解析为空", retryable=True)
        return output

    def industry_overview(self, limit: int = 12) -> dict[str, Any]:
        def fetch_side(po: int) -> list[dict[str, Any]]:
            params = {
                "pn": 1,
                "pz": max(limit, 30),
                "po": po,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fid": "f62",
                "fs": "m:90+t:2",
                "fields": "f12,f14,f3,f62,f184",
            }
            return self._eastmoney_clist(params, error_message="行业资金流不可用")

        side_rows: list[dict[str, Any]] = []
        failed_sides: list[str] = []
        for label, po in (("流入", 1), ("流出", 0)):
            try:
                side_rows.extend(fetch_side(po))
            except ProviderError:
                failed_sides.append(label)
        if not side_rows:
            raise ProviderError("eastmoney", "UPSTREAM_NETWORK", "行业资金流两端均不可用", retryable=True)
        diff = list({str(item.get("f12") or item.get("f14")): item for item in side_rows}.values())
        rows: list[dict[str, Any]] = []
        for item in diff:
            rows.append({
                "market": "A",
                "sector_name": item.get("f14") or item.get("f12"),
                "metric_kind": "net_flow",
                "metric_value": finite_number(item.get("f62")),
                "metric_unit": "CNY",
                "change_pct": finite_number(item.get("f3")),
                "net_flow_ratio": finite_number(item.get("f184")),
                "rank": 0,
                "period": "session",
                "as_of": utc_now(),
                "source": "东方财富行业资金流",
            })
        rows.sort(key=lambda row: row.get("metric_value") if row.get("metric_value") is not None else float("-inf"), reverse=True)
        half = max(1, limit // 2)
        inflows = [row for row in rows if (row.get("metric_value") or 0) > 0][:half]
        outflows = sorted(
            [row for row in rows if (row.get("metric_value") or 0) < 0],
            key=lambda row: row.get("metric_value") or 0,
        )[:max(0, limit - len(inflows))]
        selected = [*inflows, *outflows]
        if len(selected) < limit:
            selected_ids = {id(row) for row in selected}
            selected.extend(row for row in rows if id(row) not in selected_ids and len(selected) < limit)
        for rank, row in enumerate(selected, 1):
            row["rank"] = rank
            row["flow_side"] = "inflow" if (row.get("metric_value") or 0) >= 0 else "outflow"
        return {
            "rotation": selected,
            "universe_count": len(rows),
            "warnings": [f"行业资金流{label}端暂不可用" for label in failed_sides],
        }

    def industry_rotation(self, limit: int = 12) -> list[dict[str, Any]]:
        """Compatibility wrapper for callers that only need flow extremes."""
        return self.industry_overview(limit).get("rotation", [])


def risk_tags(title: str) -> list[str]:
    """Deterministic, explainable risk highlighting for intel cards."""
    text = title or ""
    keywords = {
        "监管": "监管",
        "处罚": "处罚",
        "诉讼": "诉讼",
        "减持": "减持",
        "亏损": "业绩风险",
        "下滑": "业绩风险",
        "召回": "产品风险",
        "调查": "调查",
        "风险": "风险",
        "退市": "退市风险",
    }
    return list(dict.fromkeys(tag for keyword, tag in keywords.items() if keyword in text))
