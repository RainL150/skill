"""Trusted, size-bounded page context for Ask AI."""

from __future__ import annotations

import json
from typing import Any

from dashboard.contracts import DashboardError, normalize_ts_code
from dashboard.service import DashboardService


PAGE_IDS = {"positions", "watch", "daily", "intel", "sectors", "stock", "research", "ai-settings"}
MAX_CONTEXT_CHARS = 32_000
INCLUDE_KEYS = ("portfolio", "watchlist", "notes", "news", "sector")
ANSWER_STYLE_KEYS = ("conclusion", "evidence", "counter_evidence", "discipline")
ANSWER_STYLE_LABELS = {
    "conclusion": "结论",
    "evidence": "证据",
    "counter_evidence": "反证与风险",
    "discipline": "交易纪律提醒",
}


SYSTEM_PROMPT = """你是 STJ 投研工作台里的研究助理。你只能整理信息、解释数据、提出反证与风险，不能执行交易、修改持仓或把缺失数据编成事实。

回答原则：
1. 结论先行，再列证据、反证/风险、待验证项和交易纪律提醒。
2. 数字必须来自当前上下文或只读数据工具；缺失就说缺失。
3. 区分实时、缓存、报告期数据；港美的 performance_proxy 不能称为资金净流入。
4. 涉及具体标的时，同时考虑用户的持仓/关注/交易/笔记，但不要替用户下单或承诺收益。
5. 用简洁中文，保留来源名称与日期。

个股分析框架（复杂问题默认使用；简单事实题不必机械套用）：
1. 估值：当前估值、历史分位、同业比较，以及市场已经定价了什么。
2. 资金：A 股使用真实资金流数据；港美仅可把涨跌/成交表现称为 performance_proxy，不得冒充资金流。
3. 财务质量：收入与利润趋势、盈利能力、现金流、资产负债质量和异常项。
4. 行业景气：需求、供给、价格/库存/产能周期与公司所处环节。
5. 催化剂与风险：事件时间窗、证伪条件、关键风险和需要继续跟踪的数据。

板块分析框架（用户要求“七维拆解”时使用）：
1. 需求与市场空间；2. 供给与产能；3. 产业链与价值分配；4. 竞争格局与护城河；
5. 商业模式与财务质量；6. 估值与预期差；7. 催化剂、风险信号与逻辑失效条件。

输出要求：先给结论和关键数据，再分节展开；适合比较的数据使用表格；明确关键观察、风险信号、数据缺口和来源。
"""


def normalize_descriptor(descriptor: dict[str, Any] | None) -> dict[str, Any]:
    raw = descriptor or {}
    page = str(raw.get("page") or "positions").strip().lower()
    if page not in PAGE_IDS:
        raise DashboardError("无效页面上下文", code="INVALID_CONTEXT", status=400, scope="ai.context")
    result: dict[str, Any] = {"page": page}
    if raw.get("ts_code"):
        result["ts_code"] = normalize_ts_code(str(raw["ts_code"]))
    if raw.get("sector_id") is not None:
        try:
            result["sector_id"] = int(raw["sector_id"])
        except (TypeError, ValueError) as exc:
            raise DashboardError("无效 sector_id", code="INVALID_CONTEXT", status=400, scope="ai.context") from exc
    market = str(raw.get("market") or ("A" if page == "daily" else "all")).upper()
    if market in {"A", "HK", "US"}:
        result["market"] = market
    elif market == "ALL":
        result["market"] = "all"
    scope = str(raw.get("scope") or "all").lower()
    kind = str(raw.get("kind") or "all").lower()
    if scope in {"all", "holding", "watch", "investment"}:
        result["scope"] = scope
    if kind in {"all", "news", "report", "filing", "investment_news"}:
        result["kind"] = kind
    include = raw.get("include") if isinstance(raw.get("include"), dict) else {}
    answer_style = raw.get("answer_style") if isinstance(raw.get("answer_style"), dict) else {}
    result["include"] = {key: bool(include.get(key, True)) for key in INCLUDE_KEYS}
    result["answer_style"] = {key: bool(answer_style.get(key, True)) for key in ANSWER_STYLE_KEYS}
    return result


def _trim(value: Any, depth: int = 0, *, include_notes: bool = True) -> Any:
    if depth > 6:
        return "[已截断]"
    if isinstance(value, dict):
        blocked = {"context_summary_json", "sources_json"}
        if not include_notes:
            blocked.update({"note", "notes", "recent_notes"})
        return {
            key: _trim(item, depth + 1, include_notes=include_notes)
            for key, item in value.items()
            if key not in blocked
        }
    if isinstance(value, list):
        return [_trim(item, depth + 1, include_notes=include_notes) for item in value[:20]]
    if isinstance(value, str) and len(value) > 2000:
        return value[:2000] + "…[截断]"
    return value


def build_context(service: DashboardService, descriptor: dict[str, Any] | None) -> dict[str, Any]:
    context = normalize_descriptor(descriptor)
    page = context["page"]
    include = context["include"]
    if page in {"positions", "ai-settings"}:
        response = service.portfolio()
    elif page == "watch":
        response = service.watchlist()
    elif page == "daily":
        response = service.daily_review(context.get("market", "A"))
    elif page == "intel":
        response = service.intel_radar(
            scope=context.get("scope", "all"),
            market=context.get("market", "all"),
            kind=context.get("kind", "all"),
        )
    elif page == "stock":
        if not context.get("ts_code"):
            raise DashboardError("个股上下文缺少 ts_code", code="INVALID_CONTEXT", status=400, scope="ai.context")
        response = service.stock_context(context["ts_code"])
    elif page == "research":
        response = service.research_records(limit=20)
    else:
        if context.get("sector_id") is not None:
            response = service.sector(context["sector_id"])
        else:
            response = service.sectors()
    data = _trim(response.get("data"), include_notes=include["notes"])
    extras: dict[str, Any] = {}

    def add_extra(key: str, extra_response: dict[str, Any]) -> None:
        extras[key] = {
            "data": _trim(extra_response.get("data"), include_notes=include["notes"]),
            "meta": {
                "as_of": (extra_response.get("meta") or {}).get("as_of"),
                "sources": (extra_response.get("meta") or {}).get("sources") or [],
                "warnings": (extra_response.get("meta") or {}).get("warnings") or [],
            },
            "errors": extra_response.get("errors") or [],
        }

    # Browser preferences only choose which server-owned facts are loaded. The
    # browser never supplies the facts themselves.
    if include["portfolio"] and page != "positions":
        add_extra("portfolio", service.portfolio())
    if include["watchlist"] and page != "watch":
        add_extra("watchlist", service.watchlist())
    if include["news"] and page != "intel":
        if page == "stock" and context.get("ts_code"):
            add_extra("news", service.stock_intel(context["ts_code"], "all", limit=12))
        else:
            add_extra("news", service.intel_radar(market=context.get("market", "all")))
    if include["sector"] and page != "sectors":
        add_extra("sectors", service.sectors())
    payload = {
        "descriptor": context,
        "data": data,
        "extras": extras,
        "meta": {
            "as_of": (response.get("meta") or {}).get("as_of"),
            "sources": (response.get("meta") or {}).get("sources") or [],
            "warnings": (response.get("meta") or {}).get("warnings") or [],
        },
        "errors": response.get("errors") or [],
    }
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    truncated = False
    if len(text) > MAX_CONTEXT_CHARS:
        text = text[:MAX_CONTEXT_CHARS] + "…[上下文截断]"
        truncated = True
    return {
        "descriptor": context,
        "payload": payload,
        "text": text,
        "truncated": truncated,
        "summary": {
            "page": page,
            "ts_code": context.get("ts_code"),
            "sector_id": context.get("sector_id"),
            "market": context.get("market"),
            "as_of": payload["meta"]["as_of"],
            "source_count": len(payload["meta"]["sources"]),
            "warning_count": len(payload["meta"]["warnings"]),
            "truncated": truncated,
            "includes": [key for key, enabled in include.items() if enabled],
            "answer_style": [
                ANSWER_STYLE_LABELS[key]
                for key, enabled in context["answer_style"].items()
                if enabled
            ],
        },
    }


def answer_style_instruction(context: dict[str, Any]) -> str:
    selected = [
        ANSWER_STYLE_LABELS[key]
        for key, enabled in context.get("answer_style", {}).items()
        if enabled
    ]
    if not selected:
        return "用户未指定固定回答结构；保持简洁并明确数据缺失。"
    return "用户偏好的回答结构：" + "、".join(selected) + "。"
