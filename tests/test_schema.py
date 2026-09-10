"""Story schema: JSON round-trip, legacy adapters, upsert/update."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from factory.schema.models import Character, CultivationSystem, Foreshadowing, PlotThread, WorldSetting
from factory.schema.store import SchemaStore
from factory.storage import BookRepository
from factory.workflow import SimpleWorkflow
from helpers import seed_book, settings_for


class SchemaModelTest(unittest.TestCase):
    def test_character_accepts_legacy_realm_sect_goal(self) -> None:
        card = Character.model_validate(
            {
                "id": "c1",
                "name": "陆沉",
                "aliases": "阿沉",
                "age": 17,
                "realm": "炼气期",
                "sect": "青岚宗",
                "goal": "活过试炼",
                "weapons": ["木剑"],
                "personality": ["克制", "隐忍"],
            }
        )
        self.assertEqual(card.cultivation_realm, "炼气期")
        self.assertEqual(card.faction, "青岚宗")
        self.assertEqual(card.goals, ["活过试炼"])
        self.assertEqual(card.weapons[0].name, "木剑")
        self.assertIn("克制", card.personality)
        blob = card.model_dump(mode="json")
        self.assertEqual(Character.model_validate(blob).name, "陆沉")

    def test_world_accepts_legacy_realms_sects_places(self) -> None:
        world = WorldSetting.model_validate(
            {
                "summary": "青岚宗外门",
                "rules": ["不得自造未登记境界"],
                "realms": [{"id": "r1", "name": "炼气期", "level": 1}],
                "sects": [{"id": "s1", "name": "青岚宗"}],
                "places": [{"id": "p1", "name": "外门演武场"}],
            }
        )
        self.assertEqual(world.cultivation.realms[0].name, "炼气期")
        self.assertEqual(world.cultivation.realms[0].order, 1)
        self.assertEqual(world.factions[0].type, "sect")
        self.assertEqual(world.locations[0].name, "外门演武场")
        dumped = world.to_world_json()
        self.assertEqual(dumped["sects"][0]["name"], "青岚宗")
        self.assertIn("cultivation", dumped)

    def test_plot_thread_and_foreshadowing(self) -> None:
        thread = PlotThread.model_validate(
            {"id": "t1", "text": "执事追查剑息", "related_ids": ["c1"], "chapter_no": 1, "status": "closed"}
        )
        self.assertEqual(thread.title, "执事追查剑息")
        self.assertEqual(thread.status, "resolved")
        self.assertEqual(thread.involved_characters, ["c1"])
        clue = Foreshadowing.model_validate({"clue": "旧伤中有古剑灵息", "chapter_no": 1})
        self.assertEqual(clue.inserted_at, 1)
        self.assertFalse(clue.resolved)


class SchemaStoreTest(unittest.TestCase):
    def test_save_update_character_and_thread(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            repo = seed_book(tmp)
            store = SchemaStore(repo, "demo")
            store.upsert_character(
                Character(
                    id="knowledge.character.0001",
                    name="陆沉",
                    cultivation_realm="炼气期",
                    sub_realm="后期",
                    secrets=["旧伤藏剑息"],
                )
            )
            updated = store.update_character("knowledge.character.0001", {"location": "外门演武场", "status": "alive"})
            self.assertEqual(updated.location, "外门演武场")
            self.assertEqual(updated.secrets, ["旧伤藏剑息"])
            store.upsert_plot_thread(
                PlotThread(id="thread.sword", title="执事追查剑息", involved_characters=["knowledge.character.0001"], priority=5)
            )
            store.upsert_foreshadowing(Foreshadowing(id="fs.1", clue="执事睁眼", inserted_at=1, expected_resolution="内门追查"))
            loaded = store.load()
            self.assertEqual(loaded.character_by_id("knowledge.character.0001").sub_realm, "后期")
            self.assertEqual(loaded.plot_threads[0].priority, 5)
            self.assertEqual(loaded.foreshadowing[0].clue, "执事睁眼")
            self.assertTrue((tmp / "demo" / "knowledge" / "plot.json").exists())

    def test_cultivation_merge_is_generic(self) -> None:
        system = CultivationSystem(realms=[], stages=["初期", "中期", "后期", "圆满"], power_constraints=["不可越两级硬拼"])
        other = CultivationSystem.model_validate({"resources": [{"name": "聚气丹", "type": "丹药"}]})
        merged = system.merge(other)
        self.assertEqual(merged.stages[0], "初期")
        self.assertEqual(merged.resources[0].name, "聚气丹")

    def test_workflow_writes_typed_schema(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            seed_book(tmp)
            SimpleWorkflow(settings_for(tmp), "demo").run()
            loaded = SchemaStore(BookRepository(tmp), "demo").load()
            self.assertTrue(loaded.world.summary)
            self.assertGreaterEqual(len(loaded.characters), 1)
            self.assertTrue(loaded.plot_threads)


if __name__ == "__main__":
    unittest.main()
