from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from db_schema import (
    add_sector_edge,
    add_sector_knowledge,
    add_sector_node,
    add_sector_symbol,
    add_sector_tag,
    create_sector,
    delete_sector_node,
    ensure_db,
    get_sector,
    list_sectors,
    normalize_source_url,
)
from dashboard.service import DashboardService


class SchemaTests(unittest.TestCase):
    def test_migration_is_idempotent_and_preserves_core_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "trades.db"
            conn = ensure_db(str(db))
            conn.execute(
                "INSERT INTO positions (ts_code, quantity, avg_cost, total_cost, currency) VALUES ('TEST.US', 2, 10, 20, 'USD')"
            )
            conn.commit()
            conn.close()
            conn = ensure_db(str(db))
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM positions").fetchone()["n"], 1)
            tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"sectors", "sector_nodes", "sector_edges", "research_records"}.issubset(tables))
            conn.close()

    def test_sector_crud_and_node_cascade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conn = ensure_db(str(Path(tmp) / "trades.db"))
            sector = create_sector(conn, "AI 算力", "测试")
            add_sector_tag(conn, sector["id"], "GPU")
            up = add_sector_node(conn, sector["id"], "先进封装", "upstream", bottleneck=True)
            mid = add_sector_node(conn, sector["id"], "AI 芯片", "midstream")
            add_sector_edge(conn, sector["id"], up["id"], mid["id"], "supplies")
            add_sector_symbol(conn, sector["id"], "NVDA.US", "核心")
            add_sector_knowledge(conn, sector["id"], "risk", "供应风险", "关注先进封装产能")
            full = get_sector(conn, sector["id"])
            self.assertEqual(len(full["nodes"]), 2)
            self.assertEqual(len(full["edges"]), 1)
            self.assertEqual(len(full["knowledge"]), 1)
            self.assertTrue(delete_sector_node(conn, sector["id"], up["id"]))
            self.assertEqual(get_sector(conn, sector["id"])["edges"], [])
            self.assertEqual(len(list_sectors(conn)), 1)
            conn.close()

    def test_research_record_redacts_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = DashboardService(tmp)
            response = service.save_research_record({
                "scope_type": "page",
                "question": "发生了什么？",
                "answer": "测试答案",
                "context_summary": {"api_key": "should-not-persist", "page": "positions"},
                "sources": [],
            })
            self.assertEqual(response["data"]["context_summary"]["api_key"], "[REDACTED]")
            self.assertNotIn("should-not-persist", str(response))

    def test_research_records_can_be_deleted_individually_or_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = DashboardService(tmp)
            first = service.save_research_record({
                "scope_type": "page", "question": "第一条？", "answer": "答案一",
            })["data"]
            service.save_research_record({
                "scope_type": "page", "question": "第二条？", "answer": "答案二",
            })
            deleted = service.delete_research_records(record_id=first["id"])
            self.assertTrue(deleted["data"]["deleted"])
            self.assertEqual(len(service.research_records()["data"]["records"]), 1)
            cleared = service.delete_research_records(clear_all=True)
            self.assertEqual(cleared["data"]["deleted"], 1)
            self.assertEqual(service.research_records()["data"]["records"], [])

    def test_sector_source_url_rejects_unsafe_schemes_and_credentials(self) -> None:
        self.assertEqual(normalize_source_url("https://example.com/report"), "https://example.com/report")
        for value in ("javascript:alert(1)", "https://user:pass@example.com/report", "file:///tmp/report"):
            with self.assertRaises(ValueError):
                normalize_source_url(value)


if __name__ == "__main__":
    unittest.main()
