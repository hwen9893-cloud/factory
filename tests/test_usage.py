"""Model usage SQLite log and factory stats summary."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from factory.models.usage import UsageRecord, UsageStore, format_report


class UsageStoreTest(unittest.TestCase):
    def test_summarize_today_by_agent_and_model(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            store = UsageStore(Path(raw) / "usage.sqlite")
            since = store.today_start()
            store.record(
                UsageRecord(
                    timestamp=since,
                    agent="chapter_writer",
                    provider="anthropic",
                    model="writer-x",
                    input_tokens=100,
                    output_tokens=50,
                    total_tokens=150,
                    latency=12.5,
                    success=True,
                    retry_count=0,
                    estimated_cost=0.01,
                    book_id="demo",
                )
            )
            store.record(
                UsageRecord(
                    timestamp=since,
                    agent="reviewer",
                    provider="openai",
                    model="reviewer-x",
                    input_tokens=20,
                    output_tokens=10,
                    total_tokens=30,
                    latency=8.0,
                    success=True,
                    retry_count=1,
                    estimated_cost=0.002,
                    book_id="demo",
                )
            )
            store.record(
                UsageRecord(
                    timestamp=since,
                    agent="chapter_writer",
                    provider="anthropic",
                    model="writer-x",
                    input_tokens=10,
                    output_tokens=0,
                    total_tokens=10,
                    latency=3.0,
                    success=False,
                    retry_count=2,
                    estimated_cost=None,
                    book_id="other",
                )
            )
            report = store.summarize(since=since)
            self.assertEqual(report.calls, 3)
            self.assertEqual(report.tokens, 190)
            self.assertEqual(report.failed, 1)
            self.assertAlmostEqual(report.cost or 0, 0.012)
            self.assertEqual(report.by_agent[0].name, "chapter_writer")
            self.assertEqual(report.by_agent[0].calls, 2)
            self.assertEqual(report.by_model[0].name, "writer-x")

            demo = store.summarize(since=since, book_id="demo")
            self.assertEqual(demo.calls, 2)
            self.assertEqual(demo.tokens, 180)

            text = format_report(report)
            self.assertIn("today", text)
            self.assertIn("calls    3  (1 failed)", text)
            self.assertIn("tokens   190", text)
            self.assertIn("chapter_writer", text)
            self.assertIn("writer-x", text)
            self.assertIn("$0.0120", text)

            blob = (Path(raw) / "usage.sqlite").read_bytes()
            self.assertNotIn(b"sk-", blob)
            self.assertNotIn(b"API_KEY", blob)

            latest = store.recent(book_id="demo", limit=5)
            self.assertEqual(len(latest), 2)
            self.assertEqual(latest[0].agent, "reviewer")
            self.assertNotIn("sk-", latest[0].model)

    def test_empty_store(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            store = UsageStore(Path(raw) / "usage.sqlite")
            report = store.summarize(since=store.today_start())
        self.assertEqual(report.calls, 0)
        self.assertEqual(report.tokens, 0)
        self.assertIsNone(report.cost)
        self.assertIn("—", format_report(report))


if __name__ == "__main__":
    unittest.main()
