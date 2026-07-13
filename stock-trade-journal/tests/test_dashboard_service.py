from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from db_schema import ensure_db
from dashboard.contracts import asset_ref
from dashboard.providers.a_stock import AStockProvider
from dashboard.providers.global_stock import YahooClient
from dashboard.service import DashboardService, intel_relevance_score, market_temperature


class ServiceTests(unittest.TestCase):
    def test_a_index_query_uses_declared_exchange_not_stock_prefix_heuristic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            provider = AStockProvider(tmp)
            with patch("dashboard.providers.a_stock.request_text", return_value="") as request, patch.object(provider, "_parse_tencent", return_value={}):
                provider.indices()
            url = request.call_args.args[2]
            self.assertIn("sh000001", url)
            self.assertIn("sh000300", url)
            self.assertNotIn("sz000001", url)

    def test_industry_overview_uses_constituent_breadth_and_both_flow_sides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            provider = AStockProvider(tmp)
            diff = [
                {"f12": "A", "f14": "流入一", "f3": 1.0, "f62": 800, "f184": 5, "f104": 80, "f105": 20, "f106": 2},
                {"f12": "B", "f14": "流入二", "f3": 0.2, "f62": 200, "f184": 1, "f104": 60, "f105": 40, "f106": 1},
                {"f12": "C", "f14": "流出一", "f3": -2.0, "f62": -900, "f184": -6, "f104": 10, "f105": 90, "f106": 0},
                {"f12": "D", "f14": "流出二", "f3": -0.4, "f62": -300, "f184": -2, "f104": 30, "f105": 70, "f106": 3},
            ]
            with patch.object(provider, "_eastmoney_json", return_value={"data": {"diff": diff}}):
                overview = provider.industry_overview(limit=4)
            self.assertEqual({row["flow_side"] for row in overview["rotation"]}, {"inflow", "outflow"})

    def test_market_activity_parses_real_advance_decline_counts(self) -> None:
        html = """
        <span class="market-activity-time">2026-07-10 15:00:00</span>
        <tr><td>上涨</td><td class="color-red">3511</td><td>下跌</td><td class="color-green">1612</td><td>平盘</td><td>71</td></tr>
        <tr><td>涨停</td><td>93</td><td>跌停</td><td>7</td></tr>
        """
        with tempfile.TemporaryDirectory() as tmp:
            provider = AStockProvider(tmp)
            with patch("dashboard.providers.a_stock.request_text", return_value=html):
                result = provider.market_activity()
        self.assertEqual(result["positive_count"], 3511)
        self.assertEqual(result["negative_count"], 1612)
        self.assertEqual(result["flat_count"], 71)
        self.assertEqual(result["as_of"], "2026-07-10 15:00:00")

    def test_market_leaders_excludes_listing_day_distortions_and_normalizes_symbols(self) -> None:
        rows = [
            {"f12": "301583", "f13": 0, "f14": "N新股", "f2": 216.7, "f3": 858.85, "f8": 81.35, "f100": "半导体", "f124": 1783668867},
            {"f12": "300065", "f13": 0, "f14": "海兰信", "f2": 28.79, "f3": 20.01, "f8": 18.8, "f100": "航海装备Ⅱ", "f124": 1783668894},
            {"f12": "688523", "f13": 1, "f14": "航天环宇", "f2": 61.18, "f3": 20.01, "f8": 3.99, "f100": "航天装备Ⅱ", "f124": 1783671118},
            {"f12": "000001", "f13": 0, "f14": "ST样本", "f2": 8.0, "f3": 5.0, "f8": 1.0, "f100": "银行", "f124": 1783668894},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            provider = AStockProvider(tmp)
            with patch.object(provider, "_eastmoney_json", return_value={"data": {"diff": rows}}):
                result = provider.market_leaders(limit=2)
        self.assertEqual([row["asset"]["ts_code"] for row in result], ["300065.SZ", "688523.SH"])
        self.assertEqual(result[0]["industry"], "航海装备Ⅱ")
        self.assertEqual(result[0]["change_pct"], 20.01)
        self.assertEqual(result[0]["source"], "东方财富 A 股涨幅榜")

    def test_market_temperature_is_not_derived_from_capital_flow_ranking(self) -> None:
        result = market_temperature(800, 3_200, 20, basis="fixture")
        self.assertEqual(result["breadth"], "偏弱")
        self.assertEqual(result["metric_kind"], "market_breadth")
        proxy = market_temperature(8, 2, basis="ETF fixture", proxy=True)
        self.assertEqual(proxy["label"], "代理温度")
        self.assertEqual(proxy["metric_kind"], "performance_proxy")

    def test_portfolio_quotes_are_batched_once_per_provider(self) -> None:
        def quote(code: str, price: float, currency: str, rate: float | None = None) -> dict:
            return {
                "asset": asset_ref(code, currency=currency),
                "last": price,
                "previous_close": price - 1,
                "source": "fixture",
                "cny_rate": rate,
                "cny_rate_source": "fixture-fx" if rate is not None else None,
            }

        with tempfile.TemporaryDirectory() as tmp:
            service = DashboardService(tmp)
            a_rows = {
                "600000.SH": quote("600000.SH", 10, "CNY"),
                "000001.SZ": quote("000001.SZ", 12, "CNY"),
            }
            global_rows = {
                "AAA.US": quote("AAA.US", 20, "USD", 7.0),
                "0700.HK": quote("0700.HK", 30, "HKD", 0.9),
            }
            with patch.object(service.a_stock, "quotes", return_value=a_rows) as a_batch, patch.object(
                service.yahoo, "quotes", return_value=global_rows,
            ) as global_batch:
                rows, failures, warnings = service._quotes_many(["600000.SH", "AAA.US", "000001.SZ", "0700.HK"])
        a_batch.assert_called_once_with(["600000.SH", "000001.SZ"])
        global_batch.assert_called_once_with(["AAA.US", "0700.HK"])
        self.assertFalse(failures)
        self.assertFalse(warnings)
        self.assertEqual(rows["AAA.US"]["cny_rate"], 7.0)
        self.assertEqual(rows["600000.SH"]["cny_rate"], 1.0)

    def test_global_indices_use_one_parallel_snapshot(self) -> None:
        def raw(code: str, price: float) -> dict:
            return {
                "ok": True,
                "price": price,
                "previous_close": price - 1,
                "regular_market_time": "2026-07-10T08:00:00+00:00",
            }

        snapshot = {
            "000001.SH": raw("000001.SH", 4000),
            "399006.SZ": raw("399006.SZ", 3000),
            "^HSI": raw("^HSI", 24000),
            "^HSTECH": raw("^HSTECH", 5200),
            "^GSPC": raw("^GSPC", 6500),
            "^IXIC": raw("^IXIC", 22000),
        }
        with patch("dashboard.providers.global_stock.fetch_quotes_many", return_value=snapshot) as fetch:
            rows = YahooClient().global_indices()
        fetch.assert_called_once()
        self.assertEqual(len(rows), 6)
        self.assertEqual({row["name"] for row in rows}, {"上证指数", "创业板指", "恒生指数", "恒生科技", "标普500", "纳斯达克"})

    def test_portfolio_weight_and_combined_return(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = DashboardService(tmp)
            conn = ensure_db(str(service.paths["db"]))
            conn.execute(
                "INSERT INTO positions (ts_code, quantity, avg_cost, total_cost, realized_pnl, currency) VALUES ('AAA.US', 10, 10, 100, 5, 'USD')"
            )
            conn.execute(
                "INSERT INTO positions (ts_code, quantity, avg_cost, total_cost, realized_pnl, currency) VALUES ('600000.SH', 10, 10, 100, 0, 'CNY')"
            )
            conn.commit()
            conn.close()

            def fake_quote(code: str):
                if code == "AAA.US":
                    quote = {
                        "asset": asset_ref(code, currency="USD"),
                        "last": 12,
                        "previous_close": 11,
                        "change_pct": 9.09,
                        "cny_rate": 7,
                        "source": "fixture",
                        "cache": {"stale": False},
                    }
                else:
                    quote = {
                        "asset": asset_ref(code, currency="CNY"),
                        "last": 20,
                        "previous_close": 19,
                        "change_pct": 5.26,
                        "cny_rate": 1,
                        "source": "fixture",
                        "cache": {"stale": False},
                    }
                return quote

            quote_rows = {code: fake_quote(code) for code in ("AAA.US", "600000.SH")}
            with patch.object(service, "_quotes_many", return_value=(quote_rows, {}, [])):
                result = service.portfolio()
            self.assertTrue(result["ok"])
            rows = {row["asset"]["ts_code"]: row for row in result["data"]["positions"]}
            self.assertEqual(rows["AAA.US"]["total_return_original"], 25)
            self.assertAlmostEqual(rows["AAA.US"]["return_rate"], 25)
            self.assertAlmostEqual(sum(row["weight"] for row in rows.values()), 100)
            self.assertEqual(result["data"]["summary"]["today_pnl_cny_est"], 80)

    def test_non_a_flow_is_explicitly_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = DashboardService(tmp).flow("NVDA.US")
            self.assertTrue(result["ok"])
            self.assertFalse(result["data"]["capability"]["available"])
            self.assertIn("不使用成交表现冒充", result["meta"]["warnings"][0])

    def test_chart_contract_remains_present(self) -> None:
        template = (ROOT / "templates" / "stock-chart.html").read_text(encoding="utf-8")
        for marker in ("曲线", "K线", "交易标注", "关注记录", "dataZoom", "markPoint", "markLine"):
            self.assertIn(marker, template)

    def test_intel_ranking_uses_weight_priority_recency_and_risk(self) -> None:
        fresh_holding = intel_relevance_score(
            scope="holding", holding_weight=18, published_at="2999-01-01T00:00:00+00:00", has_risk_tag=True,
        )
        old_watch = intel_relevance_score(
            scope="watch", watch_priority=1, published_at="2000-01-01T00:00:00+00:00", has_risk_tag=False,
        )
        self.assertGreater(fresh_holding, old_watch)
        self.assertEqual(
            intel_relevance_score(scope="watch", watch_priority=999),
            intel_relevance_score(scope="watch", watch_priority=5),
        )

    def test_intel_radar_loads_symbols_concurrently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = DashboardService(tmp)
            conn = ensure_db(str(service.paths["db"]))
            for code in ("AAA.US", "BBB.US"):
                conn.execute(
                    "INSERT INTO positions (ts_code, quantity, avg_cost, total_cost, realized_pnl, currency) VALUES (?, 1, 10, 10, 0, 'USD')",
                    (code,),
                )
            conn.commit()
            conn.close()
            barrier = threading.Barrier(2)

            def fake_intel(_service, code, _kind="all", limit=30):
                barrier.wait(timeout=1)
                return {
                    "data": {"items": [{
                        "id": code,
                        "kind": "news",
                        "title": code,
                        "source_url": f"https://example.com/{code}",
                        "published_at": "2026-07-10T00:00:00+00:00",
                        "risk_tags": [],
                    }]},
                    "errors": [],
                }

            portfolio = {
                "data": {"positions": [
                    {"asset": {"ts_code": "AAA.US"}, "weight": 60},
                    {"asset": {"ts_code": "BBB.US"}, "weight": 40},
                ]},
                "errors": [],
            }
            with patch.object(DashboardService, "stock_intel", new=fake_intel), patch.object(
                DashboardService, "portfolio", return_value=portfolio,
            ):
                result = service.intel_radar(scope="holding", kind="news")
        self.assertEqual({row["id"] for row in result["data"]["items"]}, {"AAA.US", "BBB.US"})


if __name__ == "__main__":
    unittest.main()
