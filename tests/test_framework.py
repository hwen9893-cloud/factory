from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from factory.framework import FrameworkImporter, FrameworkParser, ImportMode, ReferenceValidator
from factory.storage import BookRepository
from factory.workflow import SimpleWorkflow
from helpers import settings_for

FIXTURE = Path(__file__).parent / "fixtures" / "novel_framework" / "framework.md"


class FrameworkParserTest(unittest.TestCase):
    def test_markdown_to_schema_and_stable_ids(self) -> None:
        parser = FrameworkParser()
        first = parser.parse_file(FIXTURE)
        second = parser.parse_file(FIXTURE)
        self.assertEqual(first.bible.title, "古剑长夜")
        self.assertEqual(first.bible.characters[0].id, "char.luchen")
        self.assertEqual(first.bible.characters[0].id, second.bible.characters[0].id)
        self.assertEqual(first.operation_id, second.operation_id)
        self.assertEqual(first.bible.golden_fingers[0].cannot_do, ["凭空升级"])
        self.assertEqual(ReferenceValidator().validate(first.bible), [])

    def test_parser_matches_expected_fixture_contract(self) -> None:
        expected = json.loads((FIXTURE.parent / "expected_bible.json").read_text(encoding="utf-8"))
        bible = FrameworkParser().parse_file(FIXTURE).bible
        actual = {
            "schema_version": bible.schema_version,
            "title": bible.title,
            "genre": bible.genre,
            "premise": bible.premise,
            "character_ids": [item.id for item in bible.characters],
            "realm_ids": [item.id for item in bible.world.cultivation.realms],
            "faction_ids": [item.id for item in bible.world.factions],
            "location_ids": [item.id for item in bible.world.locations],
            "golden_finger_ids": [item.id for item in bible.golden_fingers],
            "antagonist_stage_ids": [item.id for item in bible.antagonist_stages],
            "main_plot_phase_ids": [item.id for item in bible.main_plot_phases],
            "payoff_rule_ids": [item.id for item in bible.payoff_rules],
            "hook_rule_ids": [item.id for item in bible.hook_rules],
            "chapter_numbers": [int(item.get("ch_no") or 0) for item in bible.chapter_outlines],
            "forbidden_rules": bible.forbidden_rules,
        }
        self.assertEqual(actual, expected)

    def test_invalid_character_faction_is_reported(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8").replace("faction.qingyun", "faction.missing", 1)
        parsed = FrameworkParser().parse(text)
        issues = ReferenceValidator().validate(parsed.bible)
        self.assertTrue(any(item.code == "UNRESOLVED_REFERENCE" for item in issues))

    def test_preview_commit_and_repeat_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = BookRepository(Path(raw))
            importer = FrameworkImporter(repo)
            preview = importer.preview("book", FIXTURE, mode=ImportMode.CREATE)
            self.assertTrue(preview.valid, preview.issues)
            bible = importer.commit(preview)
            repeated = importer.commit(preview)
            self.assertEqual(len(bible.characters), 1)
            self.assertEqual(len(repeated.characters), 1)

    def test_merge_changes_only_matching_entity(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = BookRepository(root / "books")
            importer = FrameworkImporter(repo)
            create = importer.preview("book", FIXTURE, mode=ImportMode.CREATE)
            importer.commit(create)
            changed = root / "changed.md"
            changed.write_text(FIXTURE.read_text(encoding="utf-8").replace("生存、复仇", "守护宗门"), encoding="utf-8")
            preview = importer.preview("book", changed, mode=ImportMode.MERGE)
            self.assertTrue(any(item.entity_id == "char.luchen" and item.action == "modify" for item in preview.changes))
            bible = importer.commit(preview)
            self.assertEqual(bible.characters[0].goals, ["守护宗门"])

    def test_imported_fixture_runs_full_longform_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = BookRepository(root)
            importer = FrameworkImporter(repo)
            importer.commit(importer.preview("imported", FIXTURE, mode=ImportMode.CREATE))
            result = SimpleWorkflow(settings_for(root), "imported").run(
                (
                    "chapter_planner",
                    "scene_planner",
                    "chapter_writer",
                    "continuity",
                    "reviewer",
                    "content_revision",
                    "style_polisher",
                    "memory",
                )
            )
            self.assertEqual(result["pipeline"]["status"], "completed")
            self.assertIsNotNone(repo.load_final("imported", 1))
            self.assertTrue((repo.book_dir("imported") / "state" / "current.json").exists())


if __name__ == "__main__":
    unittest.main()
