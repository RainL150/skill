#!/usr/bin/env python3
"""交易画像复盘上下文与纪律审计。"""

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from db_schema import ensure_db, get_notes, get_position, get_positions


REQUIRED_TRADE_FIELDS = {
    "main_logic": ("主逻辑",),
    "period": ("周期", "交易周期"),
    "invalid_condition": ("失效条件",),
    "add_rule": ("加仓规则", "再买规则", "加仓/再买规则"),
}

REVIEW_DEADLINE_RE = re.compile(r"(\d{4}-\d{1,2}|\d{1,2}月|复盘|中旬|下旬|上旬)")


def row_dicts(cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def workspace_db(workspace: str) -> str:
    return os.path.join(workspace, "results", "trade-journal", "db", "trades.db")


def profile_review_dir(workspace: str) -> Path:
    return Path(workspace).expanduser() / "results" / "trade-journal" / "profile-reviews"


def resolve_profile(profile_arg: Optional[str]) -> Optional[Path]:
    base = Path(__file__).resolve().parents[1] / "profiles"
    if profile_arg:
        path = Path(profile_arg)
        if path.exists():
            return path
        candidate = base / profile_arg
        if candidate.exists():
            return candidate
        if not profile_arg.endswith(".md"):
            candidate = base / f"{profile_arg}.md"
            if candidate.exists():
                return candidate
    profiles = sorted(base.glob("*.md"))
    return profiles[0] if len(profiles) == 1 else None


def parse_profile_interceptors(profile_path: Optional[Path]) -> list[dict[str, str]]:
    if not profile_path or not profile_path.exists():
        return []
    text = profile_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    in_section = False
    items: list[dict[str, str]] = []
    for line in lines:
        if line.startswith("## "):
            in_section = "交易拦截器" in line
            continue
        if not in_section:
            continue
        match = re.match(r"- `([^`]+)`[:：]\s*(.+)", line.strip())
        if match:
            items.append({"id": match.group(1), "rule": match.group(2)})
    return items


def get_trades(conn, ts_code: Optional[str] = None, limit: int = 200) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    if ts_code:
        where = "WHERE ts_code = ?"
        params.append(ts_code)
    params.append(limit)
    return row_dicts(
        conn.execute(
            f"""
            SELECT id, ts_code, exchange, side, price, quantity, amount,
                   position_before, position_after, stop_loss, take_profit,
                   note, timestamp, source, currency
            FROM trades
            {where}
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            params,
        )
    )


def get_watch(conn, ts_code: str) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT * FROM watchlist WHERE ts_code = ? AND status != 'removed'",
        (ts_code,),
    ).fetchone()
    return dict(row) if row else None


def all_ts_codes(conn) -> list[str]:
    codes: set[str] = set()
    for table in ("trades", "positions", "watchlist", "notes"):
        for row in conn.execute(f"SELECT DISTINCT ts_code FROM {table}"):
            codes.add(row["ts_code"])
    return sorted(codes)


def missing_trade_fields(note: str) -> list[str]:
    missing = []
    for field, markers in REQUIRED_TRADE_FIELDS.items():
        if not any(marker in (note or "") for marker in markers):
            missing.append(field)
    return missing


def classify_logic_drift(trades: list[dict[str, Any]], notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    trade_text = "\n".join(t.get("note") or "" for t in trades)
    reviews = [n for n in notes if n.get("note_type") == "holding_review"]
    review_text = "\n".join(n.get("note") or "" for n in reviews)

    if "策略切换" in review_text:
        findings.append(
            {
                "severity": "info",
                "type": "explicit_strategy_switch",
                "evidence": "holding_review 中已显式写入策略切换；这不是隐性漂移，但必须有新失效条件和复盘期限。",
            }
        )

    if any(word in trade_text for word in ("短线", "波段")) and any(
        word in review_text for word in ("长期", "长线", "长期看好")
    ):
        findings.append(
            {
                "severity": "high",
                "type": "period_drift",
                "evidence": "交易决策偏短线/波段，后续复盘出现长线/长期表述，需确认不是短线失败改长线。",
            }
        )

    for note in reviews:
        text = note.get("note") or ""
        if "继续持有" in text and not any(marker in text for marker in ("失效", "跌破", "退出", "复盘")):
            findings.append(
                {
                    "severity": "medium",
                    "type": "unconditional_hold",
                    "evidence": f"{note.get('timestamp')} 的 holding_review 写继续持有，但缺少失效/退出/复盘条件。",
                }
            )

    return findings


def classify_discipline_gaps(trades: list[dict[str, Any]], notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for trade in trades:
        note = trade.get("note") or ""
        missing = missing_trade_fields(note)
        if missing:
            gaps.append(
                {
                    "severity": "medium",
                    "type": "trade_decision_missing_fields",
                    "trade_id": trade.get("id"),
                    "ts_code": trade.get("ts_code"),
                    "missing": missing,
                    "evidence": "trade_decision 缺少画像要求字段，后续难以判断动作是否合规。",
                }
            )

    for note in notes:
        if note.get("note_type") != "holding_review":
            continue
        text = note.get("note") or ""
        if not REVIEW_DEADLINE_RE.search(text):
            gaps.append(
                {
                    "severity": "medium",
                    "type": "holding_review_missing_deadline",
                    "note_id": note.get("id"),
                    "evidence": "holding_review 缺少明确复盘日期/期限。",
                }
            )
        has_new_logic = any(marker in text for marker in ("新逻辑", "新主逻辑", "观察", "切到", "转为"))
        has_new_rule = any(marker in text for marker in ("失效", "跌破", "退出", "减仓"))
        if "策略切换" in text and not (has_new_logic and has_new_rule):
            gaps.append(
                {
                    "severity": "high",
                    "type": "strategy_switch_missing_new_rule",
                    "note_id": note.get("id"),
                    "evidence": "策略切换必须写新逻辑和新失效条件。",
                }
            )
    return gaps


def classify_risk_bias(
    positions: list[dict[str, Any]],
    target_position: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    total_cost = sum(float(pos.get("total_cost") or 0) for pos in positions)
    if total_cost <= 0:
        return findings

    for pos in positions:
        weight = float(pos.get("total_cost") or 0) / total_cost
        if weight >= 0.30 and (not target_position or target_position.get("ts_code") == pos.get("ts_code")):
            findings.append(
                {
                    "severity": "high" if weight >= 0.40 else "medium",
                    "type": "position_concentration",
                    "ts_code": pos.get("ts_code"),
                    "estimated_cost_weight": round(weight, 4),
                    "evidence": "按本地 total_cost 粗估仓位集中度偏高；多币种成本未换汇，只作拦截提示。",
                }
            )
    return findings


def allowed_actions_from_findings(findings: dict[str, list[dict[str, Any]]]) -> list[str]:
    actions = ["允许继续研究，但交易前必须通过画像拦截器。"]
    all_items = findings.get("logic_drift", []) + findings.get("risk_bias", []) + findings.get("discipline_gaps", [])
    types = {item.get("type") for item in all_items}
    if "position_concentration" in types:
        actions.append("仓位集中度触发拦截：默认禁止继续加仓，除非先写明新证据和减仓/退出计划。")
    if "period_drift" in types or "strategy_switch_missing_new_rule" in types:
        actions.append("疑似逻辑漂移：禁止把原交易自动延长为长期持有，必须补 holding_review。")
    if "trade_decision_missing_fields" in types:
        actions.append("交易决策字段不完整：下一次买入/加仓前必须补齐主逻辑、周期、失效条件和加仓规则。")
    if "explicit_strategy_switch" in types:
        actions.append("已显式策略切换：按新复盘期限执行，不允许无限延期。")
    return actions


def evidence_grade_hint(packet: dict[str, Any]) -> str:
    if packet.get("scope") == "single":
        trades = packet.get("trades") or []
        has_sell = any((trade.get("side") or "").upper() == "SELL" for trade in trades)
        if has_sell:
            return "A/B：该标的存在卖出或交易闭环，可进一步结合价格走势验证。"
        if packet.get("position"):
            return "B/C：该标的仍持仓中，画像结论更多依赖持仓表现、复盘笔记和外部数据。"
        return "C：该标的主要依赖观察笔记，不能升级为强画像规则。"
    return "混合：已清仓样本可评 A/B，未清仓样本多为 B/C；没有结果验证的描述只能列为待验证假设。"


def format_note_counts(note_counts: list[dict[str, Any]]) -> str:
    if not note_counts:
        return "- 暂无 notes 统计"
    return "\n".join(f"- {item['note_type']}: {item['count']}" for item in note_counts)


def market_of(ts_code: str) -> str:
    if ts_code.endswith(".US"):
        return "美股"
    if ts_code.endswith(".HK"):
        return "港股"
    if ts_code.endswith(".SH") or ts_code.endswith(".SZ"):
        return "A股"
    return "其他"


def keyword_hits(trades: list[dict[str, Any]], keywords: tuple[str, ...]) -> int:
    return sum(1 for trade in trades if any(word in (trade.get("note") or "") for word in keywords))


def unique_markets(trades: list[dict[str, Any]], positions: list[dict[str, Any]]) -> list[str]:
    codes = [item.get("ts_code") or "" for item in trades + positions]
    return sorted({market_of(code) for code in codes if code})


def code_trade_counts(trades: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for trade in trades:
        code = trade.get("ts_code")
        if code:
            counts[code] = counts.get(code, 0) + 1
    return counts


def repeated_buy_codes(trades: list[dict[str, Any]]) -> list[str]:
    counts: dict[str, int] = {}
    for trade in trades:
        if (trade.get("side") or "").upper() != "BUY":
            continue
        code = trade.get("ts_code")
        if code:
            counts[code] = counts.get(code, 0) + 1
    return [code for code, count in sorted(counts.items()) if count >= 2]


def top_positions_by_cost(positions: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    total = sum(float(pos.get("total_cost") or 0) for pos in positions)
    rows = []
    for pos in sorted(positions, key=lambda item: float(item.get("total_cost") or 0), reverse=True)[:limit]:
        cost = float(pos.get("total_cost") or 0)
        rows.append(
            {
                "ts_code": pos.get("ts_code"),
                "cost": cost,
                "weight": cost / total if total > 0 else None,
                "currency": pos.get("currency"),
            }
        )
    return rows


def behavior_metrics(packet: dict[str, Any]) -> dict[str, Any]:
    if packet.get("scope") == "single":
        trades = packet.get("trades") or []
        positions = [packet["position"]] if packet.get("position") else []
    else:
        trades = packet.get("recent_trades") or []
        positions = packet.get("positions") or []

    buys = [trade for trade in trades if (trade.get("side") or "").upper() == "BUY"]
    sells = [trade for trade in trades if (trade.get("side") or "").upper() == "SELL"]
    return {
        "trades": trades,
        "positions": positions,
        "buy_count": len(buys),
        "sell_count": len(sells),
        "markets": unique_markets(trades, positions),
        "repeated_buy_codes": repeated_buy_codes(trades),
        "top_positions": top_positions_by_cost(positions),
        "left_hits": keyword_hits(trades, ("回调", "低吸", "便宜", "错杀", "超卖", "筑底", "回落")),
        "growth_hits": keyword_hits(trades, ("增长", "财报", "AI", "业务扩张", "广告", "海外", "中长期势头")),
        "event_hits": keyword_hits(trades, ("题材", "风口", "催化", "公告", "利好", "事件")),
        "cycle_hits": keyword_hits(trades, ("商品", "供需", "库存", "轮动")),
        "long_hits": keyword_hits(trades, ("长期", "中长期", "长线")),
        "swing_hits": keyword_hits(trades, ("波段", "短线", "阶段")),
    }


def bullet_or_none(items: list[str]) -> list[str]:
    return items if items else ["暂无足够证据。"]


def format_top_positions(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["暂无当前持仓。"]
    output = []
    for item in rows:
        weight = item.get("weight")
        weight_text = f"{weight:.1%}" if weight is not None else "未估算"
        output.append(
            f"{item.get('ts_code')}：成本 {item.get('cost'):.2f} {item.get('currency') or ''}，本地成本口径权重约 {weight_text}"
        )
    return output


def extract_note_field(note: str, markers: tuple[str, ...]) -> str:
    """从结构化 note 中粗略抽取字段值，仅用于审计提示。"""
    text = note or ""
    for marker in markers:
        pattern = re.compile(rf"{re.escape(marker)}\s*[:：]\s*([^；;\n]+)")
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    return ""


def external_checks_for_note(note: str) -> list[str]:
    text = note or ""
    checks: list[str] = []
    if any(word in text for word in ("财报", "业绩", "利润", "收入", "现金流", "毛利", "指引")):
        checks.append("财报/业绩数据验证")
    if any(word in text for word in ("AI", "广告", "用户", "社区", "订阅", "DAU", "MAU")):
        checks.append("经营指标和管理层指引验证")
    if any(word in text for word in ("商品", "供需", "库存", "天气", "USDA", "种植", "收成")):
        checks.append("商品供需、库存、天气或 USDA 数据验证")
    if any(word in text for word in ("政策", "监管", "诉讼", "禁令", "反垄断")):
        checks.append("政策/监管/诉讼进展验证")
    if any(word in text for word in ("题材", "风口", "催化", "公告", "发布会", "并购", "回购")):
        checks.append("事件进展和事件后价格反应验证")
    if any(word in text for word in ("回调", "超卖", "突破", "支撑", "均线", "放量", "缩量")):
        checks.append("行情走势和技术结构验证")
    return checks or ["后续价格、持仓复盘或卖出结果验证"]


def verification_next_step(checks: list[str], has_later_sell: bool, has_followup_review: bool) -> str:
    external_checks = [check for check in checks if check != "后续价格、持仓复盘或卖出结果验证"]
    if external_checks:
        return "可立即查外部数据验证：" + "；".join(external_checks[:3])
    if has_later_sell:
        return "可立即用卖出结果和交易后走势验证"
    if has_followup_review:
        return "可用后续 holding_review 做阶段验证，但仍缺最终买卖闭环"
    return "需要未来结果：等待 holding_review、卖出闭环或新的价格/财报数据"


def verification_grade(
    trade: dict[str, Any],
    missing: list[str],
    has_followup_review: bool,
    has_later_sell: bool,
    has_external_need: bool,
) -> tuple[str, str, str]:
    side = (trade.get("side") or "").upper()
    if missing:
        return ("D", "incomplete_note", "note 字段不完整，不能用于证明好/坏习惯")
    if has_later_sell:
        return ("A", "closed_loop_available", "已有卖出/交易闭环，可结合收益和卖出纪律验证")
    if has_followup_review and side == "BUY":
        grade = "B" if not has_external_need else "B/C"
        return (grade, "reviewed_open_position", "已有持仓复盘，但仍需行情/财报等外部证据验证")
    return ("C", "unverified_note_only", "目前主要是当时 note，不能直接升级为画像规则")


def verify_trade_notes(trades: list[dict[str, Any]], notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """验证 trade_decision note 是否能支撑画像结论。"""
    notes_by_trade_id = {
        note.get("related_trade_id"): note
        for note in notes
        if note.get("note_type") == "trade_decision" and note.get("related_trade_id") is not None
    }
    notes_by_code: dict[str, list[dict[str, Any]]] = {}
    for note in notes:
        code = note.get("ts_code")
        if code:
            notes_by_code.setdefault(code, []).append(note)

    sells_by_code: dict[str, list[dict[str, Any]]] = {}
    for trade in trades:
        if (trade.get("side") or "").upper() == "SELL":
            sells_by_code.setdefault(trade.get("ts_code") or "", []).append(trade)

    verifications: list[dict[str, Any]] = []
    for trade in trades:
        if (trade.get("side") or "").upper() not in ("BUY", "SELL"):
            continue
        code = trade.get("ts_code") or ""
        linked_note = notes_by_trade_id.get(trade.get("id"))
        note_text = (linked_note or {}).get("note") or trade.get("note") or ""
        missing = missing_trade_fields(note_text)
        code_notes = notes_by_code.get(code, [])
        has_followup_review = any(note.get("note_type") == "holding_review" for note in code_notes)
        has_later_sell = any(item.get("id") != trade.get("id") for item in sells_by_code.get(code, []))
        checks = external_checks_for_note(note_text)
        next_step = verification_next_step(checks, has_later_sell, has_followup_review)
        grade, status, conclusion = verification_grade(
            trade,
            missing,
            has_followup_review,
            has_later_sell,
            any(check != "后续价格、持仓复盘或卖出结果验证" for check in checks),
        )
        verifications.append(
            {
                "trade_id": trade.get("id"),
                "ts_code": code,
                "side": trade.get("side"),
                "timestamp": trade.get("timestamp"),
                "note_id": (linked_note or {}).get("id"),
                "note_excerpt": note_text[:160],
                "main_logic": extract_note_field(note_text, REQUIRED_TRADE_FIELDS["main_logic"]),
                "period": extract_note_field(note_text, REQUIRED_TRADE_FIELDS["period"]),
                "invalid_condition": extract_note_field(note_text, REQUIRED_TRADE_FIELDS["invalid_condition"]),
                "add_rule": extract_note_field(note_text, REQUIRED_TRADE_FIELDS["add_rule"]),
                "missing_fields": missing,
                "has_followup_review": has_followup_review,
                "has_later_sell": has_later_sell,
                "external_checks_needed": checks,
                "verification_next_step": next_step,
                "can_verify_now": next_step.startswith("可立即"),
                "requires_future_outcome": next_step.startswith("需要未来结果"),
                "evidence_grade": grade,
                "verification_status": status,
                "habit_use": (
                    "can_support_profile_rule"
                    if grade in ("A", "B")
                    else "candidate_pending_verification"
                    if grade in ("B/C", "C")
                    else "do_not_use_as_profile_rule"
                ),
                "conclusion": conclusion,
            }
        )
    return verifications


def summarize_note_verification(verifications: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    usable = 0
    pending = 0
    blocked = 0
    can_verify_now = 0
    requires_future_outcome = 0
    for item in verifications:
        status = item.get("verification_status") or "unknown"
        counts[status] = counts.get(status, 0) + 1
        habit_use = item.get("habit_use")
        if habit_use == "can_support_profile_rule":
            usable += 1
        elif habit_use == "do_not_use_as_profile_rule":
            blocked += 1
        else:
            pending += 1
        if item.get("can_verify_now"):
            can_verify_now += 1
        if item.get("requires_future_outcome"):
            requires_future_outcome += 1
    return {
        "total_checked": len(verifications),
        "status_counts": counts,
        "usable_for_profile_rule": usable,
        "pending_verification": pending,
        "blocked_from_profile_rule": blocked,
        "can_verify_now": can_verify_now,
        "requires_future_outcome": requires_future_outcome,
    }


def habit_derivation(
    packet_scope: str,
    verifications: list[dict[str, Any]],
    findings: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, str]]]:
    usable = [item for item in verifications if item.get("habit_use") == "can_support_profile_rule"]
    pending = [item for item in verifications if item.get("habit_use") == "candidate_pending_verification"]
    blocked = [item for item in verifications if item.get("habit_use") == "do_not_use_as_profile_rule"]

    copyable: list[dict[str, str]] = []
    if usable:
        copyable.append(
            {
                "habit": "保留有结构的交易前记录",
                "basis": f"{len(usable)} 条交易 note 已达到 A/B 级，可用于支撑 profile 规则。",
                "rule": "继续记录主逻辑、周期、失效条件、加仓规则，并在卖出或复盘后验证。",
            }
        )

    pending_items: list[dict[str, str]] = []
    if pending:
        pending_items.append(
            {
                "habit": "低吸、分批或事件等待类动作",
                "basis": f"{len(pending)} 条 note 尚未完成验证；其中一部分可以立刻查行情、财报、事件或商品数据，另一部分必须等待后续 holding_review 或卖出闭环。",
                "next_check": "先做外部数据验证；仍无结果闭环的，只能保留为待观察，不能复制。",
            }
        )

    adjust: list[dict[str, str]] = []
    if blocked:
        adjust.append(
            {
                "habit": "note 字段缺失后仍尝试归因",
                "basis": f"{len(blocked)} 条记录字段不完整。",
                "interceptor": "缺少主逻辑、周期、失效条件、加仓规则时，不允许把该记录归纳成好习惯。",
            }
        )

    all_findings = findings.get("logic_drift", []) + findings.get("risk_bias", []) + findings.get("discipline_gaps", [])
    for finding in all_findings:
        if finding.get("type") == "position_concentration":
            adjust.append(
                {
                    "habit": "集中度升高后继续加仓",
                    "basis": finding.get("evidence", ""),
                    "interceptor": "集中度触发时，先写减仓/退出计划和新增证据，再允许讨论加仓。",
                }
            )
        elif finding.get("type") in ("period_drift", "strategy_switch_missing_new_rule"):
            adjust.append(
                {
                    "habit": "交易周期漂移",
                    "basis": finding.get("evidence", ""),
                    "interceptor": "短线/波段逻辑切到长期持有，必须先写 holding_review 和新失效条件。",
                }
            )

    return {
        "copyable_habits": copyable,
        "pending_habits": pending_items,
        "habits_to_adjust": adjust,
        "interceptor_update_basis": [
            {
                "action": "strengthen",
                "target": "note_verification_gate",
                "basis": "note 只是当时判断，不能自动证明交易质量。",
            },
            {
                "action": "keep_or_strengthen" if packet_scope == "all" else "local_check_only",
                "target": "concentration_cap_review",
                "basis": "集中度发现只证明需要交易前拦截，真实组合权重还需统一汇率口径。",
            },
        ],
    }


def format_verification_table(verifications: list[dict[str, Any]], limit: int = 12) -> list[str]:
    if not verifications:
        return ["暂无可验证的 trade_decision note。"]
    lines = [
        "| 交易 | 标的 | 状态 | 证据等级 | 本地证据 | 下一步验证 | 可否写入 profile |",
        "|------|------|------|----------|----------|----------|------------------|",
    ]
    for item in verifications[:limit]:
        local_evidence = []
        if item.get("has_later_sell"):
            local_evidence.append("有卖出闭环")
        if item.get("has_followup_review"):
            local_evidence.append("有持仓复盘")
        if item.get("missing_fields"):
            local_evidence.append("缺字段:" + ",".join(item.get("missing_fields") or []))
        if not local_evidence:
            local_evidence.append("仅 note")
        next_step = item.get("verification_next_step") or "未给出"
        lines.append(
            "| {trade_id} | {ts_code} | {status} | {grade} | {local} | {checks} | {habit_use} |".format(
                trade_id=item.get("trade_id") or "-",
                ts_code=item.get("ts_code") or "-",
                status=item.get("verification_status") or "-",
                grade=item.get("evidence_grade") or "-",
                local="、".join(local_evidence),
                checks=next_step,
                habit_use=item.get("habit_use") or "-",
            )
        )
    return lines


def format_habit_items(items: list[dict[str, str]], empty: str) -> list[str]:
    if not items:
        return [f"- {empty}"]
    lines: list[str] = []
    for item in items:
        name = item.get("habit") or item.get("target") or item.get("action") or "未命名"
        basis = item.get("basis") or ""
        rule = item.get("rule") or item.get("interceptor") or item.get("next_check") or ""
        lines.append(f"- {name}：{basis} {rule}".strip())
    return lines


def build_profile_summary_markdown(packet: dict[str, Any]) -> str:
    """生成给用户自读的画像总结报告。"""
    today = datetime.now().strftime("%Y-%m-%d")
    scope = packet.get("scope")
    metrics = behavior_metrics(packet)
    title = "交易画像总结"
    if scope == "single":
        title = f"{packet.get('ts_code')} 单标的交易画像复盘"

    findings = packet.get("audit_findings") or {}
    logic_drift = findings.get("logic_drift") or []
    risk_bias = findings.get("risk_bias") or []
    discipline_gaps = findings.get("discipline_gaps") or []
    interceptors = packet.get("profile_interceptors") or []
    actions = packet.get("allowed_actions") or []
    verifications = packet.get("note_verification") or []
    verification_summary = packet.get("note_verification_summary") or {}
    derived = packet.get("habit_derivation") or {}

    period_judgement = "偏中长期持有与中期修复"
    if metrics["swing_hits"] > 0 and metrics["long_hits"] > 0:
        period_judgement = "中长期底色里夹杂题材/波段交易"
    elif metrics["swing_hits"] > metrics["long_hits"]:
        period_judgement = "偏波段和事件兑现"

    trigger_parts = []
    if metrics["left_hits"]:
        trigger_parts.append(f"回调/低吸/超卖类触发 {metrics['left_hits']} 次")
    if metrics["growth_hits"]:
        trigger_parts.append(f"成长/财报/业务验证类触发 {metrics['growth_hits']} 次")
    if metrics["event_hits"]:
        trigger_parts.append(f"题材/事件类触发 {metrics['event_hits']} 次")
    if metrics["cycle_hits"]:
        trigger_parts.append(f"周期/商品轮动类触发 {metrics['cycle_hits']} 次")

    repeated_codes = metrics["repeated_buy_codes"]
    repeated_text = "、".join(repeated_codes) if repeated_codes else "暂无明显多次买入样本"
    markets_text = "、".join(metrics["markets"]) if metrics["markets"] else "暂无足够市场样本"

    lines = [
        f"# {title}",
        "",
        f"- 生成日期：{today}",
        f"- 复盘范围：{scope}",
        f"- 当前 profile：{packet.get('profile') or '未指定'}",
        f"- 证据等级提示：{evidence_grade_hint(packet)}",
        "",
        "## 一句话画像",
        "",
    ]

    if scope == "single":
        position = packet.get("position")
        watch = packet.get("watch")
        if position:
            lines.append(
                f"这是一笔已有持仓的标的复盘，重点不是重新描述风格，而是检查原始交易逻辑、后续复盘和当前动作是否一致。"
            )
        elif watch:
            lines.append("这是一个关注池候选标的，当前画像作用主要是限制开仓冲动和明确触发条件。")
        else:
            lines.append("本地记录较少，暂不能把该标的行为升级为画像规则。")
    else:
        summary = packet.get("summary") or {}
        lines.append(
            f"你更像“彼得·林奇式自下而上找故事 + 邓普顿式逆向低吸”的混合体，但又夹着一段明显的题材波段冲动：你会从公司、财报、AI、海外扩张、商品轮动这些线索里找中期逻辑，也愿意在回调或错杀时先上车。这个类比只描述行为相似，不代表收益能力、研究深度或纪律已经接近这些投资者；已有 {summary.get('trade_count', 0)} 条交易和 {summary.get('open_position_count', 0)} 个当前持仓，真正要验证的是：这些故事最后有没有被结果证明，而不是当时写得是否顺。"
        )

    lines.extend(
        [
            "",
            "## 样本概览",
            "",
        ]
    )
    if scope == "single":
        lines.extend(
            [
                f"- 标的：{packet.get('ts_code')}",
                f"- 交易数：{len(packet.get('trades') or [])}",
                f"- 笔记数：{len(packet.get('notes') or [])}",
                f"- 当前是否持仓：{'是' if packet.get('position') else '否'}",
            ]
        )
    else:
        summary = packet.get("summary") or {}
        lines.extend(
            [
                f"- 标的数：{summary.get('ts_code_count', 0)}",
                f"- 交易数：{summary.get('trade_count', 0)}",
                f"- 当前持仓数：{summary.get('open_position_count', 0)}",
                "- notes 结构：",
                format_note_counts(summary.get("note_counts") or []),
            ]
        )

    lines.extend(
        [
            "",
            "## 行为底色",
            "",
        ]
    )
    if scope == "single":
        lines.append(
            "这份单标的复盘不急着给你贴总标签。它要回答的是：这只票最初为什么买、后来有没有偷偷换逻辑、现在的持有或交易想法有没有被事实支持。真正有价值的不是“我当时看好”，而是这条逻辑在后续价格、财报、事件和复盘里有没有站住。"
        )
    else:
        lines.append(
            "你不像纯右侧趋势交易者，因为多数买入不是突破后追随，而是回调、低吸、估值压缩或题材尚未完全兑现时提前布局。你也不是纯长期价值投资者，因为记录里有题材波段、事件兑现、商品轮动和阶段退出。更准确的说法是：你喜欢先给自己找一个中期故事作为安全垫，再用价格回调制造入场理由。这个风格的好处是不会完全追涨，坏处是很容易把“价格更低”误读成“逻辑更强”。"
        )

    lines.extend(
        [
            "",
            "## 交易周期偏好",
            "",
            f"判断：{period_judgement}。交易笔记里同时出现长期/中长期逻辑与波段/题材兑现表述，这说明你不是纯长期持有者，也不是纯短线交易者；更准确说，你会用中长期逻辑做安全垫，再等待阶段性价格或题材兑现。",
            "",
            "证据：",
            f"- 长期/中长期相关表述命中：{metrics['long_hits']} 次。",
            f"- 波段/短线/阶段兑现相关表述命中：{metrics['swing_hits']} 次。",
            f"- 当前买入 {metrics['buy_count']} 条、卖出 {metrics['sell_count']} 条；卖出样本仍偏少，退出纪律还需要继续验证。",
            "",
            "## 买入触发方式",
            "",
            "判断：你的买入触发主要不是单纯技术突破，而是“回调后赔率改善 + 主逻辑未坏 + 题材/财报/业务验证”的组合。这个风格的优点是有安全垫意识，风险是容易把“价格更低”误当成“逻辑更强”。",
            "",
            "证据：",
            *[f"- {item}" for item in bullet_or_none(trigger_parts)],
            "",
            "## 建仓与加仓习惯",
            "",
            f"判断：你明显有分批建仓和继续加仓倾向，重复买入样本包括：{repeated_text}。这可以成为优势，但前提是每次加仓都有新证据或计划内触发条件；如果只是“原逻辑不变”，它就会退化成摊平或仓位失控。",
            "",
            "初步可复制的动作形态：先小仓验证，基本面或价格结构确认后再加；但能不能写成正式好习惯，要等下面的 note 验证和交易闭环判断。",
            "",
            "## 卖出与止损习惯",
            "",
            f"判断：你有阶段兑现和题材退出记录，但卖出样本只有 {metrics['sell_count']} 条，暂时不能证明退出纪律已经稳定。当前 profile 仍应强制要求止盈/退出条件和复盘日期。",
            "",
            "需要继续验证：盈利后是否能按计划减仓，逻辑失效时是否能退出，而不是改写成长线。",
            "",
            "## 持仓集中度",
            "",
            "判断：集中度是当前最重要的风险偏差之一。下面是本地成本口径的前三大持仓；多币种未换汇，只用于识别拦截风险，不等于真实组合权重。",
            "",
            *[f"- {item}" for item in format_top_positions(metrics["top_positions"])],
            "",
            "## 标的选择范围",
            "",
            f"判断：你的能力圈横跨 {markets_text}，还包含个股、ETF/商品、题材和成长股。范围宽是机会来源，但也要求 profile 强化“我到底懂不懂这个资产”的拦截，尤其是商品 ETF 和题材波段不能用普通成长股逻辑处理。",
            "",
            "## Note 验证：哪些只是当时想法，哪些被证据支持",
            "",
            f"判断：note 是交易当时的解释，不是事实证明。当前共审计 {verification_summary.get('total_checked', 0)} 条交易 note，其中可直接支持 profile 规则的有 {verification_summary.get('usable_for_profile_rule', 0)} 条，尚未完成验证的有 {verification_summary.get('pending_verification', 0)} 条，字段缺失或不得采纳的有 {verification_summary.get('blocked_from_profile_rule', 0)} 条。尚未完成验证不等于没法验证：其中 {verification_summary.get('can_verify_now', 0)} 条可以继续查外部数据，{verification_summary.get('requires_future_outcome', 0)} 条需要未来 holding_review 或卖出闭环。",
            "",
            *format_verification_table(verifications),
            "",
            "结论：画像更新必须先过这张表。能立刻查的数据应该继续查；必须等未来结果的样本，只能保留为观察。没有卖出闭环、后续复盘或外部行情/财报验证的 note，只能说明“当时这么想”，不能说明“这个习惯值得复制”。",
            "",
            "## 已验证/可复制好习惯",
            "",
            *format_habit_items(
                derived.get("copyable_habits") or [],
                "暂无足够 A/B 级证据把某个行为写成可复制好习惯；只能先保留为待验证假设。",
            ),
            "",
            "## 潜在优势，但必须继续验证",
            "",
            *format_habit_items(
                derived.get("pending_habits") or [],
                "当前没有足够样本把潜在优势和真实 edge 区分开。",
            ),
            "",
            "## 需要规避或调整的坏习惯",
            "",
            *format_habit_items(
                derived.get("habits_to_adjust") or [],
                "暂无足够证据定性为稳定坏习惯，但仍需继续审计。",
            ),
            "",
            "## 主要风险",
            "",
            "这套风格最大的风险不是没有逻辑，而是逻辑太容易被延长：买入时是回调低吸，跌了以后可能变成长期看好；原来是题材波段，没兑现时可能换成基本面故事；加仓时说原逻辑不变，但真正需要证明的是新增证据有没有变强。profile 的核心任务不是阻止你研究，而是在这些转换发生时把你拦下来，让你先验证再行动。",
            "",
            "## 交易质量审计",
            "",
            "这份画像不能只看 note 写得是否漂亮。当前能确认的是：你已经有较完整的交易解释习惯；还不能完全确认的是：这些解释是否稳定产生收益、是否能在失效时严格退出、是否能控制集中度。",
            "",
            "审计重点：",
            "- 买点质量：多为回调、低吸、题材或中长期逻辑驱动，但需要用后续价格和财报验证。",
            "- 加仓质量：多次加仓记录较多，必须区分新证据增强和单纯摊平。",
            "- 退出质量：卖出样本偏少，仍需观察是否能按计划止盈/止损。",
            "- 仓位质量：集中度风险需要强拦截器约束。",
            "- 结果归因：上涨可能来自市场 beta、题材或运气，不能直接归因于画像有效。",
            "",
            "## 交易拦截器摘要",
            "",
        ]
    )
    if interceptors:
        lines.extend(f"- `{item['id']}`：{item['rule']}" for item in interceptors)
    else:
        lines.append("- 当前 profile 未提供交易拦截器。")

    lines.extend(["", "## 当前审计发现", ""])
    for title_cn, items in (
        ("逻辑漂移", logic_drift),
        ("风险偏差", risk_bias),
        ("纪律缺口", discipline_gaps),
    ):
        lines.append(f"### {title_cn}")
        if not items:
            lines.append("- 暂无结构化发现。")
        else:
            for item in items:
                lines.append(f"- [{item.get('severity')}] {item.get('type')}：{item.get('evidence')}")
        lines.append("")

    lines.extend(["## 交易前提醒", ""])
    if actions:
        lines.extend(f"- {action}" for action in actions)
    else:
        lines.append("- 暂无拦截提示。")

    lines.extend(
        [
            "",
            "## 适合的 profile",
            "",
            "当前最适合继续复用 `left-opportunity-growth-value`，但它必须是“带交易拦截器的左侧机会型画像”，不是只描述偏好的静态标签。暂不建议拆出很多 profile，除非后续样本证明你在题材波段、商品周期、核心长期持有上有明显不同的纪律规则。",
            "",
            "## 为什么不是其他 profile",
            "",
            "- 不是纯右侧突破型：交易笔记更多强调回调、低吸、估值/题材未兑现，而不是突破后追随。",
            "- 不是纯长期价值型：存在题材波段、阶段兑现和事件等待，不适合完全套长期持有框架。",
            "- 不是纯短线交易型：多数买入仍带中长期主逻辑和基本面验证诉求。",
            "",
            "## Profile 草案与下一步",
            "",
            "- 第一份文档是这份给人看的画像总结，用来理解自己：交易风格、优势、风险、验证缺口和审计问题。",
            "- 第二份文档才是 profiles 侧使用的可执行规则：只保留问题、拦截器、提醒卡和更新依据。",
            "- 强化交易前拦截：无新证据不加仓、集中度过高不加仓、策略切换必须写 `holding_review`。",
            "- 每次画像更新都必须先审计 note，并只把 A/B 级证据写入正式 profile 规则。",
            "",
            "## 待验证问题",
            "",
            "- 哪些好习惯已经被完整买卖闭环验证，哪些只是 note 写得合理？",
            "- 哪些加仓来自新证据增强，哪些只是价格更低或错过买点后的补救？",
            "- 当前 profile 的拦截器是否过严或过松，需要后续复盘继续校准。",
            "",
        ]
    )
    return "\n".join(lines)


def build_executable_profile_draft_markdown(packet: dict[str, Any]) -> str:
    """生成 profiles 侧可使用的规则草案，不承担用户画像叙事。"""
    today = datetime.now().strftime("%Y-%m-%d")
    scope = packet.get("scope")
    findings = packet.get("audit_findings") or {}
    interceptors = packet.get("profile_interceptors") or []
    derived = packet.get("habit_derivation") or {}
    verification_summary = packet.get("note_verification_summary") or {}
    if scope == "single":
        title = "单标的 Profile 证据包"
        purpose = (
            "供 `profiles/` 侧后续全记录画像更新时引用；这是局部证据包，"
            "不代表已经更新整体画像，也不得单独写入全局 profile。"
        )
        fixed_rule_heading = "本次只能提出的局部拦截建议"
        update_template_heading = "进入全记录画像更新时的证据摘要模板"
        write_rule_intro = "单标的复盘不得直接新增或加强全局拦截器；只能把下面内容作为待合并证据："
        record_keep = "保留候选："
        record_add = "候选新增：note_verification_gate（如全记录复盘也支持）"
        record_strengthen = "候选加强：no_new_evidence_no_add / strategy_switch_requires_review / concentration_cap_review"
        record_downgrade = "候选降级：该标的中只有 C/D 级证据的好坏习惯"
        record_pending = "待并入全记录复盘：未清仓交易、缺少外部行情/财报验证的 note"
    else:
        title = "可执行交易 Profile 草案"
        purpose = "供 `profiles/` 侧更新规则、拦截器和交易前提醒；不是给用户自读的画像文章。"
        fixed_rule_heading = "建议写入 profile 的固定规则"
        update_template_heading = "画像更新记录模板"
        write_rule_intro = "可在用户确认后写入正式 profile 的规则："
        record_keep = "保留："
        record_add = "新增：note_verification_gate（如 profile 尚未包含）"
        record_strengthen = "加强：no_new_evidence_no_add / strategy_switch_requires_review / concentration_cap_review"
        record_downgrade = "降级：所有只有 C/D 级证据的好坏习惯"
        record_pending = "待验证：未清仓交易、缺少外部行情/财报验证的 note"
    lines = [
        f"# {title}",
        "",
        f"- 生成日期：{today}",
        f"- 复盘范围：{scope}",
        f"- 来源 profile：{packet.get('profile') or '未指定'}",
        f"- 用途：{purpose}",
        "",
        "## Note 验证门槛",
        "",
        f"- 已审计 trade_decision：{verification_summary.get('total_checked', 0)} 条。",
        f"- 可写入 profile 规则：{verification_summary.get('usable_for_profile_rule', 0)} 条。",
        f"- 尚未完成验证：{verification_summary.get('pending_verification', 0)} 条。",
        f"- 可立即继续查外部数据验证：{verification_summary.get('can_verify_now', 0)} 条。",
        f"- 需要未来 holding_review 或卖出闭环：{verification_summary.get('requires_future_outcome', 0)} 条。",
        f"- 不得采纳：{verification_summary.get('blocked_from_profile_rule', 0)} 条。",
        "- 规则：没有 A/B 级证据，不得写入“可复制好习惯”或强拦截器；C 级必须先进入外部验证或未来闭环观察。",
        "",
        "## 可复制好习惯候选",
        "",
        *format_habit_items(derived.get("copyable_habits") or [], "暂无 A/B 级可复制好习惯。"),
        "",
        "## 待验证假设",
        "",
        *format_habit_items(derived.get("pending_habits") or [], "暂无待验证假设。"),
        "",
        "## 需要规避的行为与拦截器依据",
        "",
        *format_habit_items(derived.get("habits_to_adjust") or [], "暂无需要新增强拦截的行为。"),
        "",
        "## 现有拦截器",
        "",
    ]
    if interceptors:
        lines.extend(f"- `{item['id']}`：{item['rule']}" for item in interceptors)
    else:
        lines.append("- 未读取到现有拦截器。")

    lines.extend(["", "## 审计发现到拦截器变更", ""])
    for group, items in findings.items():
        if not items:
            continue
        lines.append(f"### {group}")
        for item in items:
            lines.append(f"- [{item.get('severity')}] {item.get('type')}：{item.get('evidence')}")
        lines.append("")

    lines.extend(
        [
            f"## {fixed_rule_heading}",
            "",
            write_rule_intro,
            "",
            "- `note_verification_gate`：交易 note 只作为待验证主张；未完成卖出闭环、后续复盘或外部验证前，不得归纳为可复制好习惯。",
            "- `no_new_evidence_no_add`：加仓必须有新增证据或预设分批条件；仅“原逻辑不变”不能作为加仓理由。",
            "- `strategy_switch_requires_review`：交易周期或主逻辑切换必须写 `holding_review`，并补充新失效条件和复盘日期。",
            "- `concentration_cap_review`：集中度触发后默认禁止加仓，除非先写仓位影响、退出计划和新增证据。",
            "",
            f"## {update_template_heading}",
            "",
            "```text",
            f"日期：{today}",
            f"复盘范围：{scope}",
            "更新依据：note 验证、交易闭环、持仓复盘、风险偏差、纪律缺口",
            record_keep,
            record_add,
            record_strengthen,
            record_downgrade,
            record_pending,
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def write_profile_summary_markdown(packet: dict[str, Any], workspace: str, output: Optional[str] = None) -> Path:
    out_dir = profile_review_dir(workspace)
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    if output:
        path = Path(output).expanduser()
    elif packet.get("scope") == "single":
        code = re.sub(r"[^A-Za-z0-9_.-]+", "-", packet.get("ts_code") or "unknown")
        path = out_dir / f"{today}-{code}-self-portrait.md"
    else:
        path = out_dir / f"{today}-self-portrait.md"

    path.write_text(build_profile_summary_markdown(packet), encoding="utf-8")
    latest = out_dir / "self-portrait-latest.md"
    latest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    legacy_latest = out_dir / "profile-summary-latest.md"
    legacy_latest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def write_executable_profile_draft_markdown(packet: dict[str, Any], workspace: str, output: Optional[str] = None) -> Path:
    out_dir = profile_review_dir(workspace)
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    if output:
        path = Path(output).expanduser()
    elif packet.get("scope") == "single":
        code = re.sub(r"[^A-Za-z0-9_.-]+", "-", packet.get("ts_code") or "unknown")
        path = out_dir / f"{today}-{code}-profile-evidence.md"
    else:
        path = out_dir / f"{today}-executable-profile-draft.md"

    path.write_text(build_executable_profile_draft_markdown(packet), encoding="utf-8")
    if packet.get("scope") == "single":
        latest = out_dir / "single-profile-evidence-latest.md"
    else:
        latest = out_dir / "executable-profile-draft-latest.md"
    latest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def attach_profile_review(packet: dict[str, Any], trades: list[dict[str, Any]], notes: list[dict[str, Any]]) -> None:
    verifications = verify_trade_notes(trades, notes)
    packet["note_verification"] = verifications
    packet["note_verification_summary"] = summarize_note_verification(verifications)
    packet["habit_derivation"] = habit_derivation(
        packet.get("scope") or "unknown",
        verifications,
        packet.get("audit_findings") or {},
    )


def build_single_packet(conn, ts_code: str, profile_path: Optional[Path]) -> dict[str, Any]:
    trades = get_trades(conn, ts_code=ts_code, limit=50)
    notes = get_notes(conn, ts_code, limit=100)
    position = get_position(conn, ts_code)
    positions = get_positions(conn)
    findings = {
        "logic_drift": classify_logic_drift(trades, notes),
        "risk_bias": classify_risk_bias(positions, target_position=position),
        "discipline_gaps": classify_discipline_gaps(trades, notes),
    }
    packet = {
        "scope": "single",
        "ts_code": ts_code,
        "profile": str(profile_path) if profile_path else None,
        "profile_interceptors": parse_profile_interceptors(profile_path),
        "position": position,
        "watch": get_watch(conn, ts_code),
        "trades": trades,
        "notes": notes,
        "audit_findings": findings,
        "allowed_actions": allowed_actions_from_findings(findings),
        "review_contract": [
            "先用 profile_interceptors 拦截动作，再谈交易建议。",
            "好习惯/坏习惯必须用 trades、notes、positions 或外部行情/财报验证，不能只凭描述。",
            "如果需要更新 profile，必须输出完整复盘结论、证据等级、保留/新增/删除的拦截器。",
        ],
    }
    attach_profile_review(packet, trades, notes)
    return packet


def build_all_packet(conn, profile_path: Optional[Path]) -> dict[str, Any]:
    codes = all_ts_codes(conn)
    positions = get_positions(conn)
    trades = get_trades(conn, limit=500)
    note_counts = row_dicts(
        conn.execute(
            """
            SELECT note_type, COUNT(*) AS count
            FROM notes
            GROUP BY note_type
            ORDER BY note_type
            """
        )
    )
    notes_by_code = {
        code: get_notes(conn, code, limit=100)
        for code in codes
    }
    findings = {
        "logic_drift": [],
        "risk_bias": classify_risk_bias(positions),
        "discipline_gaps": classify_discipline_gaps(trades, [n for notes in notes_by_code.values() for n in notes]),
    }
    drift_samples = []
    for code in codes:
        drift = classify_logic_drift([t for t in trades if t.get("ts_code") == code], notes_by_code.get(code, []))
        if drift:
            drift_samples.append({"ts_code": code, "findings": drift})
            findings["logic_drift"].extend(drift)
    all_notes = [n for notes in notes_by_code.values() for n in notes]
    packet = {
        "scope": "all",
        "profile": str(profile_path) if profile_path else None,
        "profile_interceptors": parse_profile_interceptors(profile_path),
        "summary": {
            "ts_code_count": len(codes),
            "trade_count": len(trades),
            "open_position_count": len(positions),
            "note_counts": note_counts,
        },
        "positions": positions,
        "recent_trades": trades[:50],
        "logic_drift_samples": drift_samples,
        "audit_findings": findings,
        "allowed_actions": allowed_actions_from_findings(findings),
        "profile_update_contract": [
            "只把有证据支持的模式写入好习惯或坏习惯。",
            "每条好习惯必须说明复用条件和禁用条件。",
            "每条坏习惯必须变成交易拦截器，并说明触发证据。",
            "如果证据不足，保留为待验证假设，不升级为画像规则。",
        ],
    }
    attach_profile_review(packet, trades, all_notes)
    return packet


def print_packet(packet: dict[str, Any]) -> None:
    print(f"画像复盘范围: {packet['scope']}")
    if packet.get("ts_code"):
        print(f"标的: {packet['ts_code']}")
    print(f"profile: {packet.get('profile') or '未指定'}")
    print("\n交易拦截器:")
    for item in packet.get("profile_interceptors") or []:
        print(f"- {item['id']}: {item['rule']}")
    if not packet.get("profile_interceptors"):
        print("- 未从 profile 读取到拦截器")

    print("\n审计发现:")
    for group, items in (packet.get("audit_findings") or {}).items():
        print(f"\n{group}:")
        if not items:
            print("- 暂无")
            continue
        for item in items:
            print(f"- [{item.get('severity')}] {item.get('type')}: {item.get('evidence')}")

    print("\n允许动作/拦截提示:")
    for action in packet.get("allowed_actions") or []:
        print(f"- {action}")


def main() -> None:
    parser = argparse.ArgumentParser(description="交易画像复盘与纪律审计")
    parser.add_argument(
        "--workspace",
        default=os.path.expanduser(os.environ.get("STJ_WORKSPACE", "~/.trade-journal")),
        help="工作目录 (默认: STJ_WORKSPACE 或 ~/.trade-journal)",
    )
    parser.add_argument("--profile", help="profile 文件路径或 profiles/ 下的文件名")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument(
        "--write-summary",
        nargs="?",
        const="",
        help="写入给人看的画像总结 Markdown；可选指定输出路径",
    )
    parser.add_argument(
        "--write-docs",
        action="store_true",
        help="同时写入两份文档：给人看的画像总结 + profiles 侧可执行草案",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    single_parser = subparsers.add_parser("single", help="单标的画像复盘")
    single_parser.add_argument("ts_code", help="股票代码")
    single_parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    single_parser.add_argument("--write-summary", nargs="?", const="", help=argparse.SUPPRESS)
    single_parser.add_argument("--write-docs", action="store_true", help=argparse.SUPPRESS)
    all_parser = subparsers.add_parser("all", help="全记录画像更新复盘")
    all_parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    all_parser.add_argument("--write-summary", nargs="?", const="", help=argparse.SUPPRESS)
    all_parser.add_argument("--write-docs", action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args()
    db_path = workspace_db(args.workspace)
    conn = ensure_db(db_path)
    profile_path = resolve_profile(args.profile)

    if args.command == "single":
        packet = build_single_packet(conn, args.ts_code, profile_path)
    else:
        packet = build_all_packet(conn, profile_path)

    conn.close()
    summary_arg = getattr(args, "write_summary", None)
    docs_arg = getattr(args, "write_docs", False)
    if summary_arg is not None or docs_arg:
        path = write_profile_summary_markdown(packet, args.workspace, output=summary_arg or None)
        packet["self_portrait_path"] = str(path)
        packet["profile_summary_path"] = str(path)
    if docs_arg:
        draft_path = write_executable_profile_draft_markdown(packet, args.workspace)
        if packet.get("scope") == "single":
            packet["profile_evidence_path"] = str(draft_path)
        else:
            packet["executable_profile_draft_path"] = str(draft_path)

    if args.json:
        print(json.dumps(packet, ensure_ascii=False, indent=2))
    else:
        print_packet(packet)
        if summary_arg is not None or docs_arg:
            print(f"\n自读画像已写入: {path}")
        if docs_arg:
            if packet.get("scope") == "single":
                print(f"profiles 侧证据包已写入: {draft_path}")
            else:
                print(f"profiles 侧草案已写入: {draft_path}")


if __name__ == "__main__":
    main()
