"""CLI commands: init, status, continue, inspect."""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory.cli import main
from factory.settings import Settings
from helpers import seed_book, settings_for


class CliTest(unittest.TestCase):
    def test_init_status_character_list(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            settings = settings_for(tmp)

            def fake_load(*_args, **_kwargs) -> Settings:
                return settings

            buf = io.StringIO()
            with patch("factory.cli.load_settings", fake_load), patch("sys.stdout", buf):
                self.assertEqual(main(["init", "my_novel", "--title", "试炼"]), 0)
                self.assertEqual(main(["status"]), 0)
            out = buf.getvalue()
            self.assertIn("created  my_novel", out)
            self.assertIn("my_novel", out)
            self.assertTrue((tmp / "my_novel" / "meta.json").exists())
            self.assertEqual((tmp / ".current").read_text(encoding="utf-8").strip(), "my_novel")

    def test_continue_requires_architect(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            seed_book(tmp)
            settings = settings_for(tmp)

            def fake_load(*_args, **_kwargs) -> Settings:
                return settings

            err = io.StringIO()
            with patch("factory.cli.load_settings", fake_load), patch("sys.stderr", err):
                self.assertEqual(main(["continue", "--book", "demo"]), 1)
            self.assertIn("architect", err.getvalue())

    def test_continue_writes_next_chapter(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            seed_book(tmp)
            settings = settings_for(tmp)

            def fake_load(*_args, **_kwargs) -> Settings:
                return settings

            with patch("factory.cli.load_settings", fake_load):
                self.assertEqual(main(["architect", "--book", "demo"]), 0)
                self.assertEqual(main(["continue", "--book", "demo"]), 0)
            self.assertTrue((tmp / "demo" / "chapters" / "ch001" / "final.md").exists())
            self.assertTrue((tmp / "demo" / "memory" / "chapters.jsonl").exists())

            buf = io.StringIO()
            with patch("factory.cli.load_settings", fake_load), patch("sys.stdout", buf):
                self.assertEqual(main(["character", "list", "--book", "demo"]), 0)
                self.assertEqual(main(["memory", "show", "--book", "demo"]), 0)
                self.assertEqual(main(["status", "--book", "demo"]), 0)
            out = buf.getvalue()
            self.assertIn("陆沉", out)
            self.assertIn("facts", out)
            self.assertIn("next", out)

    def test_stats_after_architect(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            seed_book(tmp)
            settings = settings_for(tmp)

            def fake_load(*_args, **_kwargs) -> Settings:
                return settings

            buf = io.StringIO()
            with patch("factory.cli.load_settings", fake_load), patch("sys.stdout", buf):
                self.assertEqual(main(["architect", "--book", "demo"]), 0)
                self.assertEqual(main(["stats"]), 0)
            out = buf.getvalue()
            self.assertIn("today", out)
            self.assertIn("calls", out)
            self.assertIn("tokens", out)
            self.assertIn("cost", out)
            self.assertIn("world_builder", out)
            self.assertIn("agent", out)
            self.assertIn("model", out)
            blob = (tmp / "usage.sqlite").read_bytes()
            self.assertNotIn("灵根残缺少年".encode(), blob)

    def test_models_lists_catalog(self) -> None:
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            self.assertEqual(main(["models"]), 0)
        out = buf.getvalue()
        self.assertIn("providers", out)
        self.assertIn("qwen", out)
        self.assertIn("models", out)
        self.assertIn("writer", out)
        self.assertIn("agents", out)
        self.assertIn("chapter_writer", out)

    def test_cli_does_not_own_workflow(self) -> None:
        import inspect

        import factory.cli as cli

        source = inspect.getsource(cli)
        self.assertIn("FactoryService", source)
        self.assertNotIn("SimpleWorkflow", source)
        self.assertNotIn("BookRepository", source)
        self.assertNotIn("SchemaStore", source)
        self.assertNotIn("wf.run", source)


if __name__ == "__main__":
    unittest.main()
