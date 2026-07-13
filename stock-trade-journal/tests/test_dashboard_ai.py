from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dashboard.ai.catalog import API_MODELS, CLI_MODELS, catalog, model_for
from dashboard.ai.cli_runtime import CLI_DEFINITIONS, parse_claude_stream_line, stream_cli
from dashboard.ai.openai_runtime import AiRuntimeError, stream_chat, validate_base_url
from dashboard.ai.tools import TOOLS
from dashboard.context import SYSTEM_PROMPT, answer_style_instruction, build_context
from dashboard.contracts import envelope


class CatalogTests(unittest.TestCase):
    def test_vibe_catalog_is_complete(self) -> None:
        self.assertEqual(len(API_MODELS), 11)
        self.assertEqual(len(CLI_MODELS), 7)
        self.assertEqual(sum(1 for row in CLI_MODELS if row.get("coming_soon")), 3)
        ids = {row["id"] for row in API_MODELS}
        self.assertTrue({"deepseek-v4-flash", "deepseek-v4-pro", "gpt-4o", "MiniMax-M2", "custom"}.issubset(ids))
        self.assertEqual(catalog()["storage_key"], "stj.ai.config.v1")

    def test_fake_cli_stream_does_not_need_real_model(self) -> None:
        definition = {"bins": ["echo"], "delivery": "arg", "args": lambda _: []}
        with patch.dict(CLI_DEFINITIONS, {"fake": definition}):
            output = "".join(stream_cli("fake", "system", "user"))
        self.assertIn("system", output)
        self.assertIn("user", output)

    def test_claude_and_codex_configs_resolve_to_different_runtimes(self) -> None:
        self.assertEqual(model_for("cli-claude", "claude-code")["kind"], "claude")
        self.assertEqual(model_for("cli-codex", "codex")["kind"], "codex")

    def test_claude_stream_json_emits_partials_without_final_duplication(self) -> None:
        partial = json.dumps({
            "type": "stream_event",
            "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "回答"}},
        })
        text, seen = parse_claude_stream_line(partial)
        self.assertEqual(text, "回答")
        self.assertTrue(seen)
        duplicate, seen = parse_claude_stream_line(json.dumps({"type": "result", "result": "回答"}), seen)
        self.assertEqual(duplicate, "")
        self.assertTrue(seen)


class ContextPreferenceTests(unittest.TestCase):
    def test_system_prompt_contains_vibe_stock_and_sector_frameworks(self) -> None:
        for phrase in ("估值", "资金", "财务质量", "行业景气", "催化剂与风险", "板块分析框架", "逻辑失效条件"):
            self.assertIn(phrase, SYSTEM_PROMPT)

    def test_preferences_select_server_owned_extras_and_answer_shape(self) -> None:
        class FakeService:
            def daily_review(self, market):
                return envelope({"market": market, "note": "omit-me"})

            def portfolio(self):
                return envelope({"positions": [{"asset": {"ts_code": "TEST.US"}, "recent_notes": ["omit-me"]}]})

            def watchlist(self):
                raise AssertionError("watchlist should not be loaded")

            def intel_radar(self, **kwargs):
                raise AssertionError("news should not be loaded")

            def sectors(self):
                raise AssertionError("sectors should not be loaded")

        context = build_context(FakeService(), {
            "page": "daily",
            "market": "US",
            "include": {"portfolio": True, "watchlist": False, "notes": False, "news": False, "sector": False},
            "answer_style": {"conclusion": False, "evidence": True, "counter_evidence": False, "discipline": True},
        })
        self.assertEqual(set(context["payload"]["extras"]), {"portfolio"})
        self.assertNotIn("note", context["payload"]["data"])
        self.assertNotIn("recent_notes", context["payload"]["extras"]["portfolio"]["data"]["positions"][0])
        self.assertEqual(context["summary"]["answer_style"], ["证据", "交易纪律提醒"])
        self.assertIn("证据、交易纪律提醒", answer_style_instruction(context["descriptor"]))

    def test_research_page_uses_saved_records_as_trusted_context(self) -> None:
        class FakeService:
            def research_records(self, limit):
                self.limit = limit
                return envelope({"records": [{"id": 1, "question": "风险？", "answer": "测试"}]})

        service = FakeService()
        context = build_context(service, {
            "page": "research",
            "include": {"portfolio": False, "watchlist": False, "notes": False, "news": False, "sector": False},
        })
        self.assertEqual(service.limit, 20)
        self.assertEqual(context["payload"]["data"]["records"][0]["question"], "风险？")


class SsrfTests(unittest.TestCase):
    def test_local_mode_allows_loopback_but_public_mode_blocks_it(self) -> None:
        self.assertEqual(validate_base_url("http://127.0.0.1:11434", public_mode=False), "http://127.0.0.1:11434/v1")
        with self.assertRaises(AiRuntimeError):
            validate_base_url("http://127.0.0.1:11434", public_mode=True)

    def test_metadata_is_always_blocked(self) -> None:
        with self.assertRaises(AiRuntimeError):
            validate_base_url("http://169.254.169.254/latest", public_mode=False)


class _FakeOpenAIHandler(BaseHTTPRequestHandler):
    calls = 0

    def log_message(self, format, *args):  # noqa: A003 - BaseHTTPRequestHandler signature.
        return

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler contract.
        length = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        type(self).calls += 1
        if type(self).calls == 1 and body.get("tools"):
            events = [
                {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call-1", "function": {"name": "market_get_quote", "arguments": '{"ts_code":"NVDA.US"}'}}]}}]},
            ]
        else:
            events = [
                {"choices": [{"delta": {"content": "基于工具数据："}}]},
                {"choices": [{"delta": {"content": "测试完成"}}]},
            ]
        payload = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
        raw = payload.encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class OpenAIStreamTests(unittest.TestCase):
    def test_tool_loop_and_ndjson_events(self) -> None:
        _FakeOpenAIHandler.calls = 0
        server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeOpenAIHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            events = list(stream_chat(
                {"baseURL": f"http://127.0.0.1:{server.server_port}", "apiKey": "test-key", "model": "test-model"},
                [{"role": "user", "content": "测试"}],
                tools=TOOLS,
                execute_tool=lambda name, args: {
                    "ok": True,
                    "data": {"last": 100},
                    "meta": {"sources": [{"name": "fixture"}]},
                    "errors": [],
                },
                public_mode=False,
            ))
        finally:
            server.shutdown()
            server.server_close()
        types = [event["type"] for event in events]
        self.assertIn("tool_start", types)
        self.assertIn("tool_result", types)
        self.assertIn("delta", types)
        self.assertEqual(types[-1], "done")
        self.assertEqual(events[-1]["sources"], [{"name": "fixture"}])


if __name__ == "__main__":
    unittest.main()
