"""Agent contracts: validation, continuity rules, reviewer isolation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from factory.agents.architect import OutlineAgent
from factory.agents.base import SchemaValidationError
from factory.agents.quality import collect_continuity_issues
from factory.workflow import SimpleWorkflow
from helpers import CHARACTERS, seed_book, settings_for


class AgentTest(unittest.TestCase):
    def test_outline_requires_seed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            seed_book(tmp)
            workflow = SimpleWorkflow(settings_for(tmp), "demo")
            agent = OutlineAgent(workflow.runtime)
            with self.assertRaises(SchemaValidationError):
                agent.run({})

    def test_continuity_detects_dead_character(self) -> None:
        characters = [dict(CHARACTERS[0]), dict(CHARACTERS[1])]
        characters[0]["status"] = "dead"
        issues = collect_continuity_issues("陆沉出现在演武场。", characters)
        types = {item["type"] for item in issues}
        self.assertIn("dead_character_appears", types)

    def test_reviewer_does_not_write_continuity_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            repo = seed_book(tmp)
            repo.save_draft("demo", 1, "第1章", "陆沉站在青岚宗演武场，赵衡正在挑衅。")
            workflow = SimpleWorkflow(settings_for(tmp), "demo")
            result = workflow.run(("reviewer",))
            self.assertIn("review", result)
            self.assertTrue((tmp / "demo" / "chapters" / "ch001" / "review.json").exists())
            self.assertFalse((tmp / "demo" / "chapters" / "ch001" / "continuity.json").exists())


if __name__ == "__main__":
    unittest.main()
