"""Shared HTTP primitives and classified provider errors."""

from __future__ import annotations

import json
import time
from typing import Any

import requests


USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) STJ-Dashboard/1.0"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class ProviderError(RuntimeError):
    def __init__(self, provider: str, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.provider = provider
        self.code = code
        self.retryable = retryable


def session(*, trust_env: bool = True) -> requests.Session:
    client = requests.Session()
    client.trust_env = trust_env
    client.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json,text/plain,*/*"})
    return client


def _read_limited(response: requests.Response, max_bytes: int = MAX_RESPONSE_BYTES) -> bytes:
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            raise ProviderError("http", "RESPONSE_TOO_LARGE", "上游响应超过大小限制")
        chunks.append(chunk)
    return b"".join(chunks)


def request_json(
    provider: str,
    client: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: tuple[float, float] = (5.0, 15.0),
    retries: int = 1,
) -> Any:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = client.get(
                url,
                params=params,
                headers=headers,
                timeout=timeout,
                stream=True,
                allow_redirects=True,
            )
            if response.status_code == 403:
                raise ProviderError(provider, "UPSTREAM_FORBIDDEN", "上游拒绝访问", retryable=False)
            if response.status_code == 429:
                raise ProviderError(provider, "UPSTREAM_RATE_LIMIT", "上游限流", retryable=True)
            if response.status_code >= 500:
                raise ProviderError(provider, "UPSTREAM_5XX", f"上游 HTTP {response.status_code}", retryable=True)
            if response.status_code >= 400:
                raise ProviderError(provider, "UPSTREAM_HTTP", f"上游 HTTP {response.status_code}")
            raw = _read_limited(response)
            try:
                return json.loads(raw.decode(response.encoding or "utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ProviderError(provider, "UPSTREAM_SCHEMA", "上游返回了无效 JSON") from exc
        except ProviderError as exc:
            last_error = exc
            if not exc.retryable or attempt >= retries:
                raise
        except requests.Timeout as exc:
            last_error = ProviderError(provider, "UPSTREAM_TIMEOUT", "上游请求超时", retryable=True)
            if attempt >= retries:
                raise last_error from exc
        except requests.RequestException as exc:
            last_error = ProviderError(provider, "UPSTREAM_NETWORK", f"上游连接失败：{exc}", retryable=True)
            if attempt >= retries:
                raise last_error from exc
        time.sleep(0.4 * (attempt + 1))
    raise last_error or ProviderError(provider, "UPSTREAM_UNKNOWN", "上游请求失败")


def request_text(
    provider: str,
    client: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    encoding: str = "utf-8",
    timeout: tuple[float, float] = (5.0, 15.0),
) -> str:
    try:
        response = client.get(url, params=params, timeout=timeout, stream=True, allow_redirects=True)
        if response.status_code >= 400:
            raise ProviderError(provider, "UPSTREAM_HTTP", f"上游 HTTP {response.status_code}", retryable=response.status_code >= 500)
        return _read_limited(response).decode(encoding, errors="replace")
    except ProviderError:
        raise
    except requests.Timeout as exc:
        raise ProviderError(provider, "UPSTREAM_TIMEOUT", "上游请求超时", retryable=True) from exc
    except requests.RequestException as exc:
        raise ProviderError(provider, "UPSTREAM_NETWORK", f"上游连接失败：{exc}", retryable=True) from exc
