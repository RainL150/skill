#!/usr/bin/env python3
"""Stream one trusted STJ Ask AI request as NDJSON."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import uuid
from typing import Any

from dashboard.ai.catalog import model_for
from dashboard.ai.cli_runtime import CliUnavailable, stream_cli, terminate_active
from dashboard.ai.openai_runtime import AiRuntimeError, stream_chat
from dashboard.ai.tools import TOOLS, execute_tool
from dashboard.context import SYSTEM_PROMPT, answer_style_instruction, build_context
from dashboard.contracts import DashboardError
from dashboard.service import DEFAULT_WORKSPACE, DashboardService


MAX_BODY_CHARS = 512 * 1024
MAX_MESSAGE_CHARS = 20_000
MAX_MESSAGES = 12


def emit(event: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def read_request() -> dict[str, Any]:
    raw = sys.stdin.read(MAX_BODY_CHARS + 1)
    if len(raw) > MAX_BODY_CHARS:
        raise DashboardError("聊天请求超过大小限制", code="BODY_TOO_LARGE", status=413, scope="ai")
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise DashboardError("聊天请求不是有效 JSON", code="INVALID_JSON", status=400, scope="ai") from exc
    if not isinstance(payload, dict):
        raise DashboardError("聊天请求必须是对象", code="INVALID_JSON", status=400, scope="ai")
    return payload


def normalize_messages(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise DashboardError("messages 必须是数组", code="INVALID_MESSAGES", status=400, scope="ai")
    output = []
    for item in value[-MAX_MESSAGES:]:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        output.append({"role": item["role"], "content": content[:MAX_MESSAGE_CHARS]})
    if not output or output[-1]["role"] != "user":
        raise DashboardError("最后一条消息必须是用户问题", code="INVALID_MESSAGES", status=400, scope="ai")
    return output


def _signal_handler(signum, frame) -> None:  # noqa: ARG001 - signal callback signature.
    terminate_active()
    raise SystemExit(128 + signum)


def run(workspace: str) -> int:
    request = read_request()
    messages = normalize_messages(request.get("messages"))
    llm = request.get("llm") if isinstance(request.get("llm"), dict) else {}
    service = DashboardService(workspace)
    context = build_context(service, request.get("context") if isinstance(request.get("context"), dict) else {})
    request_id = str(uuid.uuid4())
    mode = str(llm.get("mode") or ("cli" if str(llm.get("provider") or "").startswith("cli-") else "api"))
    provider = str(llm.get("provider") or "")
    model = str(llm.get("model") or "")
    definition = model_for(provider, model)
    if mode == "cli" and (not definition or not definition.get("kind") or definition.get("coming_soon")):
        raise DashboardError("不支持或尚未开放的 CLI 配置", code="INVALID_AI_CONFIG", status=400, scope="ai")
    emit({
        "type": "meta",
        "request_id": request_id,
        "mode": mode,
        "model": model,
        "model_label": definition.get("name") if definition else model,
        "provider": provider,
        "runtime_kind": definition.get("kind") if definition else None,
        "context": context["summary"],
    })
    structure = answer_style_instruction(context["descriptor"])
    system = (
        f"{SYSTEM_PROMPT}\n\n{structure}"
        f"\n\n当前页面可信上下文（JSON，可能含显式缺失/错误）：\n{context['text']}"
    )
    if mode == "cli":
        emit({"type": "status", "stage": "generating", "message": f"{definition['name']} 已接收请求，正在生成"})
        user_prompt = "\n\n".join(f"{item['role']}: {item['content']}" for item in messages)
        for chunk in stream_cli(definition["kind"], system, user_prompt):
            emit({"type": "delta", "text": chunk})
        emit({
            "type": "done",
            "trace": [],
            "rounds": 1,
            "sources": context["payload"]["meta"]["sources"],
            "tool_calling": False,
        })
        return 0

    api_messages = [{"role": "system", "content": system}, *messages]
    public_mode = os.environ.get("STJ_PUBLIC_MODE") == "1" or bool(os.environ.get("STJ_API_KEY", "").strip())
    for event in stream_chat(
        llm,
        api_messages,
        tools=TOOLS,
        execute_tool=lambda name, args: execute_tool(service, name, args),
        public_mode=public_mode,
    ):
        emit(event)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Stream one STJ Ask AI request as NDJSON")
    parser.add_argument(
        "--workspace",
        default=os.path.expanduser(os.environ.get("STJ_WORKSPACE", DEFAULT_WORKSPACE)),
        help="工作目录 (默认: STJ_WORKSPACE 或 ~/.trade-journal)",
    )
    args = parser.parse_args()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, _signal_handler)
    try:
        return run(args.workspace)
    except (DashboardError, AiRuntimeError, CliUnavailable, RuntimeError) as exc:
        emit({
            "type": "error",
            "code": getattr(exc, "code", "AI_ERROR"),
            "message": str(exc),
            "retryable": bool(getattr(exc, "retryable", False)),
        })
        return 1
    finally:
        terminate_active()


if __name__ == "__main__":
    raise SystemExit(main())
