"""Atomic provider cache and cross-process request throttling."""

from __future__ import annotations

import hashlib
import json
import os
import random
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from dashboard.contracts import CONTRACT_VERSION, json_safe

try:
    import fcntl
except ImportError:  # pragma: no cover - macOS/Linux production path has fcntl.
    fcntl = None


@dataclass(frozen=True)
class CacheEntry:
    value: Any
    age_seconds: float
    fresh: bool
    path: Path


class AtomicJsonCache:
    """Small, secret-free JSON cache with stale inspection support."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)

    def key_path(self, provider: str, operation: str, params: dict[str, Any]) -> Path:
        payload = json.dumps(
            {
                "contract": CONTRACT_VERSION,
                "provider": provider,
                "operation": operation,
                "params": json_safe(params),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        safe_provider = "".join(ch for ch in provider if ch.isalnum() or ch in "-_")[:32] or "provider"
        safe_operation = "".join(ch for ch in operation if ch.isalnum() or ch in "-_")[:48] or "data"
        return self.root / f"{safe_provider}-{safe_operation}-{digest}.json"

    def get(
        self,
        provider: str,
        operation: str,
        params: dict[str, Any],
        ttl_seconds: float,
    ) -> CacheEntry | None:
        path = self.key_path(provider, operation, params)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if payload.get("contract_version") != CONTRACT_VERSION:
                return None
            created_at = float(payload["created_at_epoch"])
            age = max(0.0, time.time() - created_at)
            return CacheEntry(payload.get("value"), age, age <= ttl_seconds, path)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            quarantine = path.with_suffix(f".corrupt-{int(time.time())}.json")
            try:
                os.replace(path, quarantine)
            except OSError:
                pass
            return None

    def set(self, provider: str, operation: str, params: dict[str, Any], value: Any) -> Path:
        path = self.key_path(provider, operation, params)
        payload = {
            "contract_version": CONTRACT_VERSION,
            "created_at_epoch": time.time(),
            "value": json_safe(value),
        }
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=self.root)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
            os.chmod(path, 0o600)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        return path

    def fetch(
        self,
        provider: str,
        operation: str,
        params: dict[str, Any],
        *,
        ttl_seconds: float,
        loader: Callable[[], Any],
        allow_stale: bool = True,
        force_refresh: bool = False,
    ) -> tuple[Any, dict[str, Any], list[str]]:
        entry = self.get(provider, operation, params, ttl_seconds)
        if entry and entry.fresh and not force_refresh:
            return entry.value, {
                "hit": True,
                "stale": False,
                "age_seconds": round(entry.age_seconds, 3),
            }, []
        try:
            value = loader()
            self.set(provider, operation, params, value)
            return value, {"hit": False, "stale": False, "age_seconds": 0}, []
        except Exception as exc:
            if entry and allow_stale:
                return entry.value, {
                    "hit": True,
                    "stale": True,
                    "age_seconds": round(entry.age_seconds, 3),
                }, [f"实时来源失败，使用 {int(entry.age_seconds)} 秒前缓存：{exc}"]
            raise


class CrossProcessRateGate:
    """Serialize a provider across dashboard Python processes."""

    _fallback_lock = threading.Lock()

    def __init__(self, root: str | Path, name: str, min_interval: float, jitter: tuple[float, float] = (0.0, 0.0)) -> None:
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(ch for ch in name if ch.isalnum() or ch in "-_") or "provider"
        self.path = self.root / f".{safe_name}-rate-gate"
        self.min_interval = max(0.0, min_interval)
        self.jitter = jitter

    def wait(self) -> None:
        if fcntl is None:
            with self._fallback_lock:
                self._wait_locked(None)
            return
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            self._wait_locked(fd)
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def _wait_locked(self, fd: int | None) -> None:
        last = 0.0
        if fd is not None:
            os.lseek(fd, 0, os.SEEK_SET)
            raw = os.read(fd, 64).decode("ascii", errors="ignore").strip()
            try:
                last = float(raw)
            except ValueError:
                last = 0.0
        elapsed = time.time() - last
        delay = self.min_interval - elapsed
        if delay > 0:
            delay += random.uniform(*self.jitter)
            time.sleep(delay)
        now = time.time()
        if fd is not None:
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.write(fd, f"{now:.6f}".encode("ascii"))
            os.fsync(fd)
