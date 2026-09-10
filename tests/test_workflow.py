"""End-to-end mock workflow and CLI."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from factory.cli import main
from factory.workflow import SimpleWorkflow
from helpers import seed_book, settings_for


class WorkflowTest(unittest.TestCase):
    def test_full_pipeline_writes_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            seed_book(tmp)
            result = SimpleWorkflow(settings_for(tmp), "demo").run()
            self.assertIn("outline", result)
            self.assertIn("architecture", result)
            self.assertIn("chapter_plan", result)
            self.assertIn("body", result)
            self.assertIn("review", result)
            self.assertIn("continuity", result)
            self.assertIn("memory_update", result)
            chapter = tmp / "demo" / "chapters" / "ch001"
            self.assertTrue((tmp / "demo" / "architecture.json").exists())
            self.assertTrue((tmp / "demo" / "outline.json").exists())
            self.assertTrue((tmp / "demo" / "volumes" / "v001" / "plan.json").exists())
            self.assertTrue((chapter / "plan.json").exists())
            self.assertTrue((chapter / "draft.md").exists())
            self.assertTrue((chapter / "continuity.json").exists())
            self.assertTrue((chapter / "review.json").exists())
            self.assertTrue((chapter / "final.md").exists())
            self.assertTrue((tmp / "demo" / "memory" / "summaries.jsonl").exists())
            self.assertTrue((tmp / "demo" / "memory" / "canon.json").exists())
            self.assertTrue((tmp / "demo" / "memory" / "chapters.jsonl").exists())

    def test_cli_init_and_run(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            settings = settings_for(tmp)
            from unittest.mock import patch
            from factory.settings import Settings

            def fake_load(*_args, **_kwargs) -> Settings:
                return settings

            with patch("factory.cli.load_settings", fake_load):
                self.assertEqual(main(["init", "cli-book", "--seed", "一个钩子"]), 0)
                self.assertEqual(main(["architect", "--book", "cli-book"]), 0)
                self.assertEqual(main(["continue", "--book", "cli-book"]), 0)
            self.assertTrue((tmp / "cli-book" / "outline.json").exists())
            self.assertTrue((tmp / "cli-book" / "chapters" / "ch001" / "final.md").exists())


if __name__ == "__main__":
    unittest.main()
