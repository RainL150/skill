from __future__ import annotations

import json
import requests
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from dashboard.cache import AtomicJsonCache, CrossProcessRateGate
from dashboard.contracts import asset_ref, envelope, finite_number, market_group, normalize_ts_code
from dashboard.providers.a_stock import AStockProvider
from dashboard.providers.global_stock import YahooClient
from dashboard.providers.base import ProviderError, request_json


class ContractTests(unittest.TestCase):
    def test_market_and_null_contract(self) -> None:
        self.assertEqual(market_group("600519.SH"), "A")
        self.assertEqual(market_group("0700.HK"), "HK")
        self.assertEqual(market_group("NVDA.US"), "US")
        self.assertEqual(normalize_ts_code("nvda.us"), "NVDA.US")
        self.assertIsNone(finite_number("-"))
        self.assertIsNone(finite_number(float("nan")))
        self.assertEqual(finite_number("0"), 0.0)
        self.assertEqual(asset_ref("0700.HK")["currency"], "HKD")

    def test_envelope_is_stable(self) -> None:
        result = envelope({"value": float("inf")}, warnings=["stale"])
        self.assertTrue(result["ok"])
        self.assertIsNone(result["data"]["value"])
        self.assertEqual(result["meta"]["contract_version"], "dashboard-v1")
        self.assertEqual(result["meta"]["warnings"], ["stale"])


class CacheTests(unittest.TestCase):
    def test_force_refresh_bypasses_a_fresh_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = AtomicJsonCache(tmp)
            cache.set("test", "quote", {"code": "A"}, {"price": 1})
            value, meta, warnings = cache.fetch(
                "test",
                "quote",
                {"code": "A"},
                ttl_seconds=60,
                loader=lambda: {"price": 2},
                force_refresh=True,
            )
            self.assertEqual(value["price"], 2)
            self.assertFalse(meta["hit"])
            self.assertFalse(warnings)

    def test_fresh_stale_and_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = AtomicJsonCache(tmp)
            cache.set("test", "quote", {"code": "A"}, {"price": 1})
            entry = cache.get("test", "quote", {"code": "A"}, 60)
            self.assertIsNotNone(entry)
            self.assertTrue(entry.fresh)
            time.sleep(0.02)
            value, meta, warnings = cache.fetch(
                "test",
                "quote",
                {"code": "A"},
                ttl_seconds=0,
                loader=lambda: (_ for _ in ()).throw(RuntimeError("offline")),
            )
            self.assertEqual(value["price"], 1)
            self.assertTrue(meta["stale"])
            self.assertIn("offline", warnings[0])
            entry.path.write_text("{broken", encoding="utf-8")
            self.assertIsNone(cache.get("test", "quote", {"code": "A"}, 60))
            self.assertTrue(list(Path(tmp).glob("*.corrupt-*.json")))

    def test_cross_process_gate_waits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            gate = CrossProcessRateGate(tmp, "test", 0.03)
            gate.wait()
            started = time.monotonic()
            gate.wait()
            self.assertGreaterEqual(time.monotonic() - started, 0.02)


class ProviderParserTests(unittest.TestCase):
    def test_http_errors_are_classified_without_live_network(self) -> None:
        class Response:
            encoding = "utf-8"

            def __init__(self, status, body=b"{}"):
                self.status_code = status
                self.body = body

            def iter_content(self, chunk_size):
                yield self.body

        class Client:
            def __init__(self, value):
                self.value = value

            def get(self, *args, **kwargs):
                if isinstance(self.value, Exception):
                    raise self.value
                return self.value

        with self.assertRaises(ProviderError) as rate_limit:
            request_json("fixture", Client(Response(429)), "https://example.test", retries=0)
        self.assertEqual(rate_limit.exception.code, "UPSTREAM_RATE_LIMIT")
        self.assertTrue(rate_limit.exception.retryable)
        with self.assertRaises(ProviderError) as timeout:
            request_json("fixture", Client(requests.Timeout()), "https://example.test", retries=0)
        self.assertEqual(timeout.exception.code, "UPSTREAM_TIMEOUT")
        with self.assertRaises(ProviderError) as schema:
            request_json("fixture", Client(Response(200, b"not-json")), "https://example.test", retries=0)
        self.assertEqual(schema.exception.code, "UPSTREAM_SCHEMA")

    def test_tencent_parser_preserves_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            provider = AStockProvider(tmp)
            values = [""] * 53
            values[1] = "测试公司"
            values[3] = "12.50"
            values[4] = "12.00"
            values[31] = "0.50"
            values[32] = "4.17"
            values[39] = ""
            values[46] = "2.30"
            payload = 'v_sh600000="' + "~".join(values) + '";'
            parsed = provider._parse_tencent(payload)["600000"]
            self.assertEqual(parsed["price"], 12.5)
            self.assertIsNone(parsed["pe_ttm"])
            self.assertEqual(parsed["pb"], 2.3)

    def test_yahoo_financial_normalization(self) -> None:
        fixture = json.loads((ROOT / "tests" / "fixtures" / "providers" / "yahoo-timeseries.json").read_text(encoding="utf-8"))
        client = YahooClient()
        with patch("dashboard.providers.global_stock.request_json", return_value=fixture):
            result = client.financials("TEST.US", "annual")
        row = result["series"][0]
        self.assertEqual(row["free_cash_flow"], 100)
        self.assertEqual(row["gross_margin"], 40)
        self.assertEqual(row["operating_cash_ratio"], 1.6)
        self.assertEqual(row["debt_ratio"], 40)


if __name__ == "__main__":
    unittest.main()
