"""Read-only function tools exposed to OpenAI-compatible models."""

from __future__ import annotations

from typing import Any

from dashboard.contracts import DashboardError, normalize_ts_code
from dashboard.service import DashboardService


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "stj_get_portfolio_context",
            "description": "读取当前持仓、权重、盈亏、关注和提醒。只读。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stj_get_symbol_context",
            "description": "读取单一标的的持仓、关注、交易、笔记和公司概览。",
            "parameters": {
                "type": "object",
                "properties": {"ts_code": {"type": "string", "description": "统一代码，如 NVDA.US / 0700.HK / 600519.SH"}},
                "required": ["ts_code"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "market_get_quote",
            "description": "查询 A/港/美单一标的规范化行情与报价时间。",
            "parameters": {"type": "object", "properties": {"ts_code": {"type": "string"}}, "required": ["ts_code"], "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "market_get_company_profile",
            "description": "查询公司主营业务、行业、地区和关键公司资料。",
            "parameters": {"type": "object", "properties": {"ts_code": {"type": "string"}}, "required": ["ts_code"], "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "market_get_valuation",
            "description": "查询当前 PE/PB/PS/前向估值与分析师目标；不可得分位保持 null。",
            "parameters": {"type": "object", "properties": {"ts_code": {"type": "string"}}, "required": ["ts_code"], "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "market_get_financials",
            "description": "查询标准化年度或季度财务序列和质量指标。",
            "parameters": {
                "type": "object",
                "properties": {"ts_code": {"type": "string"}, "period": {"type": "string", "enum": ["annual", "quarterly"]}},
                "required": ["ts_code"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "market_get_news",
            "description": "查询单一标的近期新闻，最多 20 条。",
            "parameters": {"type": "object", "properties": {"ts_code": {"type": "string"}}, "required": ["ts_code"], "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "market_get_reports",
            "description": "查询单一标的近期研报或分析师评级动态，最多 20 条。",
            "parameters": {"type": "object", "properties": {"ts_code": {"type": "string"}}, "required": ["ts_code"], "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "market_get_sector_context",
            "description": "读取用户维护的板块标签、产业链、关联标的和核心知识。",
            "parameters": {"type": "object", "properties": {"sector_id": {"type": "integer", "minimum": 1}}, "required": ["sector_id"], "additionalProperties": False},
        },
    },
]


def _code(args: dict[str, Any]) -> str:
    return normalize_ts_code(str(args.get("ts_code") or ""))


def execute_tool(service: DashboardService, name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "stj_get_portfolio_context":
        return service.portfolio()
    if name == "stj_get_symbol_context":
        return service.stock_context(_code(args))
    if name == "market_get_quote":
        return service.quote(_code(args))
    if name == "market_get_company_profile":
        response = service.stock_context(_code(args))
        response["data"] = {"asset": response["data"]["asset"], "company_profile": response["data"]["company_profile"]}
        return response
    if name == "market_get_valuation":
        response = service.stock_context(_code(args))
        response["data"] = {"asset": response["data"]["asset"], "valuation": response["data"]["valuation"]}
        return response
    if name == "market_get_financials":
        period = str(args.get("period") or "annual")
        if period not in {"annual", "quarterly"}:
            raise DashboardError("period 必须是 annual 或 quarterly", code="INVALID_TOOL_ARGS", status=400, scope="ai.tool")
        return service.financials(_code(args), period)
    if name == "market_get_news":
        return service.stock_intel(_code(args), "news", limit=20)
    if name == "market_get_reports":
        return service.stock_intel(_code(args), "report", limit=20)
    if name == "market_get_sector_context":
        try:
            sector_id = int(args.get("sector_id"))
        except (TypeError, ValueError) as exc:
            raise DashboardError("sector_id 必须是正整数", code="INVALID_TOOL_ARGS", status=400, scope="ai.tool") from exc
        return service.sector(sector_id)
    raise DashboardError(f"未知只读工具：{name}", code="UNKNOWN_TOOL", status=400, scope="ai.tool")
