"""OpenAI-compatible streaming and bounded read-only tool loop."""

from __future__ import annotations

import ipaddress
import json
import socket
from typing import Any, Callable, Iterator
from urllib.parse import urljoin, urlparse

import requests


MAX_TOOL_ROUNDS = 6
MAX_TOOL_RESULT_CHARS = 6000
MAX_INTERNAL_RESULT_CHARS = 50_000
MAX_REDIRECTS = 3


class AiRuntimeError(RuntimeError):
    def __init__(self, message: str, *, code: str = "AI_ERROR", retryable: bool = False, status: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.status = status


def _blocked_ip(value: str, public_mode: bool) -> bool:
    ip = ipaddress.ip_address(value)
    if ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        return True
    if public_mode and (ip.is_private or ip.is_loopback):
        return True
    return False


def validate_base_url(value: str, *, public_mode: bool) -> str:
    parsed = urlparse((value or "").strip())
    if parsed.scheme not in {"http", "https"}:
        raise AiRuntimeError("Base URL 必须使用 http:// 或 https://", code="INVALID_BASE_URL", status=400)
    if parsed.username or parsed.password:
        raise AiRuntimeError("Base URL 不能包含用户名或密码", code="INVALID_BASE_URL", status=400)
    if not parsed.hostname:
        raise AiRuntimeError("Base URL 缺少主机名", code="INVALID_BASE_URL", status=400)
    try:
        port = parsed.port
    except ValueError as exc:
        raise AiRuntimeError("Base URL 端口无效", code="INVALID_BASE_URL", status=400) from exc
    if port is not None and not 1 <= port <= 65535:
        raise AiRuntimeError("Base URL 端口无效", code="INVALID_BASE_URL", status=400)
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise AiRuntimeError("Base URL 域名无法解析", code="BASE_URL_DNS", retryable=True, status=400) from exc
    if any(_blocked_ip(address, public_mode) for address in addresses):
        raise AiRuntimeError("Base URL 指向了不允许的本机、内网或元数据地址", code="SSRF_BLOCKED", status=400)
    base = value.rstrip("/")
    if not base.endswith(("/v1", "/v3", "/api/v3")):
        base += "/v1"
    return base


def _post_stream(client: requests.Session, url: str, headers: dict[str, str], payload: dict[str, Any], *, public_mode: bool) -> requests.Response:
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        validate_base_url(current.rsplit("/chat/completions", 1)[0], public_mode=public_mode)
        try:
            response = client.post(current, headers=headers, json=payload, timeout=(10, 120), stream=True, allow_redirects=False)
        except requests.Timeout as exc:
            raise AiRuntimeError("模型接口超时", code="AI_TIMEOUT", retryable=True, status=504) from exc
        except requests.RequestException as exc:
            raise AiRuntimeError(f"模型接口连接失败：{exc}", code="AI_NETWORK", retryable=True) from exc
        if response.status_code in {301, 302, 307, 308} and response.headers.get("location"):
            current = urljoin(current, response.headers["location"])
            continue
        if response.status_code == 401:
            raise AiRuntimeError("模型 API Key 无效或无权限", code="AI_UNAUTHORIZED", status=401)
        if response.status_code == 429:
            raise AiRuntimeError("模型接口限流", code="AI_RATE_LIMIT", retryable=True, status=429)
        if response.status_code >= 400:
            body = response.text[:300]
            raise AiRuntimeError(f"模型接口 HTTP {response.status_code}: {body}", code=f"AI_HTTP_{response.status_code}", retryable=response.status_code >= 500, status=502)
        return response
    raise AiRuntimeError("模型接口重定向过多", code="AI_REDIRECT", status=502)


def _iter_sse(response: requests.Response) -> Iterator[dict[str, Any]]:
    total = 0
    for raw in response.iter_lines(decode_unicode=False):
        if not raw:
            continue
        total += len(raw)
        if total > 16 * 1024 * 1024:
            raise AiRuntimeError("模型响应超过大小限制", code="AI_RESPONSE_TOO_LARGE")
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        choices = payload.get("choices") or []
        if choices:
            yield choices[0].get("delta") or {}


def _result_count(value: Any) -> int | None:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        for key in ("items", "positions", "watchlist", "series", "sectors", "records"):
            if isinstance(value.get(key), list):
                return len(value[key])
    return None


def stream_chat(
    config: dict[str, Any],
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]],
    execute_tool: Callable[[str, dict[str, Any]], dict[str, Any]],
    public_mode: bool,
) -> Iterator[dict[str, Any]]:
    base = validate_base_url(str(config.get("baseURL") or ""), public_mode=public_mode)
    api_key = str(config.get("apiKey") or "")
    model = str(config.get("model") or "").strip()
    if not api_key or not model:
        raise AiRuntimeError("API 模式缺少 API Key 或 Model", code="INVALID_AI_CONFIG", status=400)
    client = requests.Session()
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    trace: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    tool_enabled = True

    for round_number in range(1, MAX_TOOL_ROUNDS + 1):
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.3,
            "stream": True,
        }
        if tool_enabled:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            response = _post_stream(client, f"{base}/chat/completions", headers, payload, public_mode=public_mode)
        except AiRuntimeError as exc:
            if tool_enabled and exc.code in {"AI_HTTP_400", "AI_HTTP_404", "AI_HTTP_422"}:
                tool_enabled = False
                yield {"type": "meta", "tool_calling": False, "warning": "当前兼容端点不接受工具定义，已降级为预装上下文回答"}
                continue
            raise

        content_parts: list[str] = []
        tool_accumulator: dict[int, dict[str, str]] = {}
        for delta in _iter_sse(response):
            if delta.get("content"):
                text = str(delta["content"])
                content_parts.append(text)
                yield {"type": "delta", "text": text}
            for tool_call in delta.get("tool_calls") or []:
                index = tool_call.get("index")
                if index is None:
                    call_id = str(tool_call.get("id") or "")
                    index = next((key for key, value in tool_accumulator.items() if call_id and value["id"] == call_id), None)
                    if index is None:
                        index = len(tool_accumulator) if call_id or not tool_accumulator else max(tool_accumulator)
                accumulator = tool_accumulator.setdefault(int(index), {"id": "", "name": "", "arguments": ""})
                if tool_call.get("id"):
                    accumulator["id"] = str(tool_call["id"])
                function = tool_call.get("function") or {}
                if function.get("name"):
                    accumulator["name"] = str(function["name"])
                if function.get("arguments"):
                    accumulator["arguments"] += str(function["arguments"])

        if not tool_accumulator:
            yield {"type": "done", "trace": trace, "rounds": round_number, "sources": sources, "tool_calling": tool_enabled}
            return

        assistant_calls = []
        for index in sorted(tool_accumulator):
            item = tool_accumulator[index]
            assistant_calls.append({
                "id": item["id"] or f"tool-{round_number}-{index}",
                "type": "function",
                "function": {"name": item["name"], "arguments": item["arguments"]},
            })
        messages.append({"role": "assistant", "content": "".join(content_parts) or None, "tool_calls": assistant_calls})

        for call in assistant_calls:
            function = call["function"]
            try:
                args = json.loads(function.get("arguments") or "{}")
                if not isinstance(args, dict):
                    args = {}
            except json.JSONDecodeError:
                args = {}
            yield {"type": "tool_start", "tool": function["name"], "args": args}
            error_message = None
            try:
                result = execute_tool(function["name"], args)
            except Exception as exc:
                error_message = str(exc)
                result = {"ok": False, "error": error_message}
            internal = json.dumps(result, ensure_ascii=False, separators=(",", ":"))[:MAX_INTERNAL_RESULT_CHARS]
            injected = internal[:MAX_TOOL_RESULT_CHARS]
            truncated = len(internal) > MAX_TOOL_RESULT_CHARS
            count = _result_count(result.get("data") if isinstance(result, dict) else result)
            result_sources = ((result.get("meta") or {}).get("sources") or []) if isinstance(result, dict) else []
            for source in result_sources:
                if source and source not in sources:
                    sources.append(source)
            trace.append({"tool": function["name"], "args": args, "error": error_message, "truncated": truncated})
            yield {"type": "tool_result", "tool": function["name"], "count": count, "truncated": truncated, "error": error_message, "sources": result_sources}
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": injected})

    # Close a model that keeps asking for tools with one final tool-free stream.
    payload = {"model": model, "messages": messages, "temperature": 0.3, "stream": True}
    response = _post_stream(client, f"{base}/chat/completions", headers, payload, public_mode=public_mode)
    for delta in _iter_sse(response):
        if delta.get("content"):
            yield {"type": "delta", "text": str(delta["content"])}
    yield {"type": "done", "trace": trace, "rounds": MAX_TOOL_ROUNDS, "sources": sources, "tool_calling": False}
