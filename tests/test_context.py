"""StoryContext and repository round-trip."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from factory.context import StoryContext
from helpers import seed_book


class ContextTest(unittest.TestCase):
    def test_load_snapshot_fields(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = seed_book(Path(raw))
            ctx = StoryContext.load(repo, "demo")
        self.assertEqual(ctx.genre, "修仙爽文")
        self.assertEqual(ctx.characters[0]["id"], "knowledge.character.0001")
        self.assertEqual(ctx.character_by_id("knowledge.character.0001")["name"], "陆沉")
        self.assertIn("story_seed", ctx.prompt_vars())
        self.assertIn("story_title", ctx.prompt_vars())
        self.assertEqual(ctx.prompt_vars()["story_title"], ctx.title)

    def test_prev_tail_and_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = seed_book(Path(raw))
            repo.save_final("demo", 1, "第1章", "前文。" + ("尾" * 20))
            repo.append_summary("demo", 1, "试炼反击")
            meta = repo.load_meta("demo")
            meta["current_chapter"] = 2
            repo.save_meta("demo", meta)
            ctx = StoryContext.load(repo, "demo", prev_tail_chars=10)
        self.assertIn("尾", ctx.prev_tail())
        self.assertIn("试炼反击", ctx.recent_summary_text())


if __name__ == "__main__":
    unittest.main()
