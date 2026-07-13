"""Vibe-compatible AI provider catalog used by settings and chat validation."""

from __future__ import annotations

from typing import Any


API_MODELS: list[dict[str, Any]] = [
    {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash", "provider": "deepseek", "base_url": "https://api.deepseek.com", "description": "DeepSeek 官方 · 快而省"},
    {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro", "provider": "deepseek", "base_url": "https://api.deepseek.com", "description": "DeepSeek 官方 · 旗舰推理"},
    {"id": "deepseek-ai/DeepSeek-V3", "name": "SiliconFlow · DeepSeek V3", "provider": "silicon", "base_url": "https://api.siliconflow.cn/v1", "description": "硅基流动"},
    {"id": "gpt-4o", "name": "OpenAI GPT-4o", "provider": "openai", "base_url": "https://api.openai.com/v1", "description": "OpenAI"},
    {"id": "MiniMax-M2", "name": "MiniMax M2", "provider": "minimax", "base_url": "https://api.minimaxi.com/v1", "description": "MiniMax"},
    {"id": "doubao-pro", "name": "豆包 Pro", "provider": "openai-compatible", "base_url": "", "description": "model 填火山方舟 ep-… 接入点"},
    {"id": "openai/gpt-4o", "name": "OpenRouter · GPT-4o", "provider": "openrouter", "base_url": "https://openrouter.ai/api/v1", "description": "可修改任意模型 id"},
    {"id": "llama-3.3-70b-versatile", "name": "Groq · Llama 3.3 70B", "provider": "groq", "base_url": "https://api.groq.com/openai/v1", "description": "Groq"},
    {"id": "meta-llama/Llama-3.3-70B-Instruct-Turbo", "name": "Together · Llama 3.3 70B", "provider": "together", "base_url": "https://api.together.xyz/v1", "description": "Together AI"},
    {"id": "mimo-v2.5-pro", "name": "MiMo V2.5 Pro", "provider": "mimo", "base_url": "", "description": "需自有网关"},
    {"id": "custom", "name": "其它 OpenAI 兼容", "provider": "openai-compatible", "base_url": "", "description": "自填 Base URL 与 model"},
]

CLI_MODELS: list[dict[str, Any]] = [
    {"id": "claude-code", "name": "Claude Code", "provider": "cli-claude", "kind": "claude", "description": "用本机 Claude 订阅"},
    {"id": "qwen-code", "name": "Qwen Code", "provider": "cli-qwen", "kind": "qwen", "description": "通义 Qwen Code 订阅", "security_note": "当前 CLI 非交互参数可能启用自动权限，运行前请确认本机版本"},
    {"id": "deepseek-cli", "name": "DeepSeek CLI", "provider": "cli-deepseek", "kind": "deepseek", "description": "DeepSeek 本机 CLI 订阅", "security_note": "部分版本需要将 prompt 放入本机进程参数"},
    {"id": "codex", "name": "Codex", "provider": "cli-codex", "kind": "codex", "description": "OpenAI Codex 订阅"},
    {"id": "opencode", "name": "OpenCode", "provider": "cli-opencode", "kind": "opencode", "description": "OpenCode 订阅", "coming_soon": True},
    {"id": "cursor-agent", "name": "Cursor Agent", "provider": "cli-cursor", "kind": "cursor", "description": "Cursor Agent 订阅", "coming_soon": True},
    {"id": "kimi", "name": "Kimi", "provider": "cli-kimi", "kind": "kimi", "description": "Kimi 订阅", "coming_soon": True},
]


def model_for(provider: str, model: str) -> dict[str, Any] | None:
    return next((item for item in [*API_MODELS, *CLI_MODELS] if item["provider"] == provider and item["id"] == model), None)


def catalog(cli_status: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    statuses = cli_status or {}
    cli = []
    for item in CLI_MODELS:
        row = dict(item)
        row.update(statuses.get(item["kind"], {}))
        row.setdefault("available", False if item.get("coming_soon") else None)
        cli.append(row)
    return {
        "storage_key": "stj.ai.config.v1",
        "active_config_count": 1,
        "cli": cli,
        "api": [dict(item) for item in API_MODELS],
        "modes": {
            "cli": {"stream": True, "function_calling": False, "context_preloaded": True},
            "api": {"stream": True, "function_calling": True, "context_preloaded": True},
        },
    }
