"""PromptManager loads Markdown templates and substitutes {{variables}}."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from factory.prompts import REQUIRED_HEADINGS, PromptManager, substitute


PACKAGED = (
    "architect",
    "world_builder",
    "character",
    "outline",
    "volume_planner",
    "chapter_planner",
    "chapter_writer",
    "continuity",
    "reviewer",
    "revision",
    "memory_extract",
)


class PromptManagerTest(unittest.TestCase):
    def test_packaged_prompts_have_required_sections(self) -> None:
        manager = PromptManager()
        for name in PACKAGED:
            sections = manager.load_sections(name)
            for heading in REQUIRED_HEADINGS:
                self.assertIn(heading, sections, f"{name}.md missing #{heading}")
            loaded = manager.load(name)
            self.assertTrue(loaded["system"], f"{name} Role/system is empty")
            self.assertIn("# Output Format", loaded["user"])

    def test_packaged_outline_prompt(self) -> None:
        manager = PromptManager()
        loaded = manager.load("outline")
        self.assertIn("大纲", loaded["system"])
        self.assertIn("{{story_seed}}", loaded["user"])
        rendered = manager.render(
            "outline",
            story_seed="种子",
            genre="修仙",
            style="短句",
            story_title="试炼",
            world={},
            characters=[],
            target_chapters=3,
            architecture={},
        )
        self.assertIn("种子", rendered["user"])
        self.assertNotIn("{{story_seed}}", rendered["user"])
        self.assertIn("试炼", rendered["user"])
        self.assertNotIn("{{story_title}}", rendered["user"])

    def test_markdown_without_headings_is_user_only(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "writer").mkdir()
            (root / "writer" / "note.md").write_text("写：{{title}}", encoding="utf-8")
            loaded = PromptManager(root).load("writer/note")
        self.assertEqual(loaded["system"], "")
        self.assertEqual(loaded["user"], "写：{{title}}")

    def test_role_becomes_system(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "sample.md").write_text(
                "# Role\n系统身份\n\n# Objective\n目标 {{story_title}}\n\n"
                "# Input\n{{genre}}\n\n# Requirements\n要求\n\n"
                "# Constraints\n限制\n\n# Output Format\nJSON\n",
                encoding="utf-8",
            )
            manager = PromptManager(root)
            loaded = manager.load("sample")
            rendered = manager.render("sample", story_title="甲", genre="修仙")
        self.assertEqual(loaded["system"], "系统身份")
        self.assertIn("# Objective", loaded["user"])
        self.assertNotIn("# Role", loaded["user"])
        self.assertIn("甲", rendered["user"])
        self.assertIn("修仙", rendered["user"])

    def test_substitute_keeps_json_braces(self) -> None:
        text = substitute('{"title": "{{title}}", "other": {"a": 1}}', {"title": "甲"})
        self.assertEqual(text, '{"title": "甲", "other": {"a": 1}}')

    def test_continuity_placeholder_exists(self) -> None:
        loaded = PromptManager().load("continuity")
        self.assertIn("连续", loaded["system"])
        self.assertIn("{{world_context}}", loaded["user"])
        self.assertIn("{{character_context}}", loaded["user"])

    def test_world_context_alias_from_canon(self) -> None:
        rendered = PromptManager().render("continuity", canon={"rules": ["不可飞升"]})
        self.assertIn("不可飞升", rendered["user"])
        self.assertNotIn("{{world_context}}", rendered["user"])


if __name__ == "__main__":
    unittest.main()
