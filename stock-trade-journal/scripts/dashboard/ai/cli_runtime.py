"""Stream local subscription CLIs from an isolated temporary directory."""

from __future__ import annotations

import atexit
import json
import os
import queue
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Iterator


CLI_TIMEOUT_SECONDS = 300
MAX_ARG_BYTES = 110_000
_ACTIVE: set[subprocess.Popen] = set()
_ACTIVE_LOCK = threading.Lock()


class CliUnavailable(RuntimeError):
    pass


CLI_DEFINITIONS: dict[str, dict] = {
    "claude": {
        "bins": ["claude", "openclaude"],
        "delivery": "system-file",
        "args": lambda system_file: [
            "-p", "--output-format", "stream-json", "--include-partial-messages", "--verbose",
            "--system-prompt-file", system_file,
            "--disallowedTools", "Read", "Write", "Edit", "Glob", "Grep", "Bash",
            "NotebookEdit", "WebFetch", "WebSearch", "TodoWrite", "Task",
        ],
    },
    "qwen": {
        "bins": ["qwen"],
        "delivery": "stdin",
        "args": lambda _: ["--yolo"],
        "security_note": "Qwen 非交互模式由上游 CLI 控制权限；STJ 只在空临时目录运行",
    },
    "deepseek": {
        "bins": ["deepseek", "codewhale"],
        "delivery": "arg",
        "args": lambda _: ["exec", "--auto"],
        "security_note": "DeepSeek prompt 可能短暂出现在本机进程参数中",
    },
    "codex": {
        "bins": ["codex"],
        "delivery": "stdin",
        "args": lambda _: ["exec", "--sandbox", "read-only", "--skip-git-repo-check", "-"],
    },
}


EXTRA_PATHS = [
    "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin",
    str(Path.home() / ".local" / "bin"), str(Path.home() / ".npm-global" / "bin"),
    str(Path.home() / ".bun" / "bin"), str(Path.home() / ".deno" / "bin"),
    str(Path.home() / ".yarn" / "bin"),
]


def _find_binary(candidates: list[str]) -> str | None:
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
        for directory in EXTRA_PATHS:
            path = Path(directory) / candidate
            if path.is_file() and os.access(path, os.X_OK):
                return str(path)
    return None


def detect_cli(kind: str) -> str | None:
    definition = CLI_DEFINITIONS.get(kind)
    return _find_binary(definition["bins"]) if definition else None


def capability_status() -> dict[str, dict]:
    output = {}
    for kind, definition in CLI_DEFINITIONS.items():
        path = detect_cli(kind)
        output[kind] = {
            "available": bool(path),
            "binary": Path(path).name if path else None,
            "security_note": definition.get("security_note"),
        }
    return output


def _minimal_environment() -> dict[str, str]:
    allowed = {
        "HOME", "PATH", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "LC_CTYPE",
        "TERM", "TMPDIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
    }
    env = {key: value for key, value in os.environ.items() if key in allowed}
    env["PATH"] = os.pathsep.join([env.get("PATH", ""), *EXTRA_PATHS])
    return env


def _register(process: subprocess.Popen) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE.add(process)


def _unregister(process: subprocess.Popen) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE.discard(process)


def terminate_active() -> None:
    with _ACTIVE_LOCK:
        processes = list(_ACTIVE)
    for process in processes:
        if process.poll() is not None:
            continue
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            process.terminate()
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and any(process.poll() is None for process in processes):
        time.sleep(0.05)
    for process in processes:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                process.kill()


atexit.register(terminate_active)


def _redact_stderr(value: str) -> str:
    text = value or ""
    for marker in ("api_key", "apikey", "authorization", "token", "secret"):
        text = text.replace(marker, "[REDACTED]")
    return text[:400]


def parse_claude_stream_line(line: str, text_seen: bool = False) -> tuple[str, bool]:
    """Extract one visible text delta from Claude Code stream-json output.

    Claude emits partial ``stream_event`` rows and later repeats the complete answer in
    ``assistant``/``result`` rows. Once a partial was seen, final rows must be ignored or
    the UI receives the whole answer twice.
    """
    raw = (line or "").strip()
    if not raw:
        return "", text_seen
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return raw, text_seen or bool(raw)
    if not isinstance(event, dict):
        return "", text_seen
    if event.get("type") == "stream_event":
        stream_event = event.get("event") if isinstance(event.get("event"), dict) else {}
        delta = stream_event.get("delta") if isinstance(stream_event.get("delta"), dict) else {}
        if stream_event.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
            text = str(delta.get("text") or "")
            return text, text_seen or bool(text)
    if text_seen:
        return "", True
    if event.get("type") == "result":
        text = str(event.get("result") or "")
        return text, bool(text)
    if event.get("type") == "assistant":
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        content = message.get("content") if isinstance(message.get("content"), list) else []
        text = "".join(str(item.get("text") or "") for item in content if isinstance(item, dict) and item.get("type") == "text")
        return text, bool(text)
    return "", text_seen


def stream_cli(kind: str, system_prompt: str, user_prompt: str) -> Iterator[str]:
    definition = CLI_DEFINITIONS.get(kind)
    binary = detect_cli(kind)
    if not definition or not binary:
        raise CliUnavailable(f"未检测到 {kind} CLI；请先安装并登录，或改用 API 接入")
    combined = f"{system_prompt}\n\n{user_prompt}".strip()
    temp_dir = tempfile.mkdtemp(prefix="stj-ai-")
    process: subprocess.Popen | None = None
    try:
        if definition["delivery"] == "system-file":
            system_file = Path(temp_dir) / "system.txt"
            system_file.write_text(system_prompt, encoding="utf-8")
            os.chmod(system_file, 0o600)
            args = definition["args"](str(system_file))
            stdin_payload = user_prompt
        elif definition["delivery"] == "stdin":
            args = definition["args"](None)
            stdin_payload = combined
        else:
            if len(combined.encode("utf-8")) > MAX_ARG_BYTES:
                raise RuntimeError(f"提示词超过 {kind} 的 {MAX_ARG_BYTES} 字节上限")
            args = [*definition["args"](None), combined]
            stdin_payload = None
        process = subprocess.Popen(
            [binary, *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=temp_dir,
            env=_minimal_environment(),
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        _register(process)
        if stdin_payload is not None and process.stdin:
            try:
                process.stdin.write(stdin_payload)
                process.stdin.flush()
            except BrokenPipeError:
                pass
        if process.stdin:
            process.stdin.close()

        output_queue: queue.Queue[str | None] = queue.Queue()
        stderr_parts: list[str] = []

        def pump_stdout() -> None:
            try:
                if process and process.stdout:
                    for line in process.stdout:
                        output_queue.put(line)
            finally:
                output_queue.put(None)

        def pump_stderr() -> None:
            if process and process.stderr:
                for line in process.stderr:
                    if sum(len(part) for part in stderr_parts) < 2000:
                        stderr_parts.append(line)

        threading.Thread(target=pump_stdout, daemon=True).start()
        threading.Thread(target=pump_stderr, daemon=True).start()
        deadline = time.monotonic() + CLI_TIMEOUT_SECONDS
        emitted = False
        claude_text_seen = False
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"{kind} 生成超时（>{CLI_TIMEOUT_SECONDS}s）")
            try:
                chunk = output_queue.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                continue
            if chunk is None:
                break
            if kind == "claude":
                text, claude_text_seen = parse_claude_stream_line(chunk, claude_text_seen)
            else:
                text = chunk
            if text:
                emitted = True
                yield text
        return_code = process.wait(timeout=10)
        if return_code != 0 and not emitted:
            raise RuntimeError(f"{kind} 退出码 {return_code}：{_redact_stderr(''.join(stderr_parts))}")
    finally:
        if process is not None:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    process.terminate()
            for stream in (process.stdout, process.stderr, process.stdin):
                if stream is not None and not stream.closed:
                    try:
                        stream.close()
                    except OSError:
                        pass
            _unregister(process)
        shutil.rmtree(temp_dir, ignore_errors=True)
