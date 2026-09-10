"""Layered story memory: retrieve slices, merge extracts, persist JSON/SQLite."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from factory.memory.retriever import MemoryRetriever
from factory.memory.store import JsonMemoryStore, MemoryError, SqliteMemoryStore, build_store
from factory.memory.types import ChapterMemory, CharacterEntity, PlotThread
from factory.memory.updater import MemoryUpdater
from factory.workflow import SimpleWorkflow
from helpers import seed_book, settings_for


class MemoryTest(unittest.TestCase):
    def test_json_roundtrip_and_hydrate(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            repo = seed_book(tmp)
            store = JsonMemoryStore(repo, "demo")
            memory = store.load()
            self.assertIn("青岚宗", memory.canon.world_summary)
            self.assertEqual(memory.entities.characters["knowledge.character.0001"].name, "陆沉")
            self.assertTrue((tmp / "demo" / "memory" / "canon.json").exists())

    def test_retriever_excludes_unrelated_character_and_old_bodies(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            repo = seed_book(tmp)
            store = JsonMemoryStore(repo, "demo")
            memory = store.load()
            memory.entities.characters["knowledge.character.0099"] = CharacterEntity(
                id="knowledge.character.0099",
                name="路人甲",
                note="不该进入写手上下文",
            )
            memory.plot.open_threads = [
                PlotThread(
                    id="thread.sword",
                    text="执事追查剑息",
                    related_ids=["knowledge.character.0001"],
                ),
                PlotThread(
                    id="thread.unrelated",
                    text="南海秘闻",
                    related_ids=["knowledge.character.0099"],
                ),
            ]
            store.save(memory)
            store.save_chapter_memory(ChapterMemory(ch_no=1, summary="第一章摘要", events=["试炼"]))
            store.save_chapter_memory(ChapterMemory(ch_no=2, summary="第二章摘要"))
            repo.save_final("demo", 1, "第1章", "这一章很长" * 50)
            repo.save_final("demo", 2, "第2章", "只有文末可见XYZ")
            retriever = MemoryRetriever(store, repo, "demo", recent_chapters=2, prev_tail_chars=20)
            ctx = retriever.for_writer(
                3,
                chapter_plan={
                    "scenes": [
                        {
                            "pov_char": "knowledge.character.0001",
                            "present_chars": ["knowledge.character.0001", "knowledge.character.0002"],
                        }
                    ]
                },
            )
        names = {item["name"] for item in ctx.characters}
        self.assertIn("陆沉", names)
        self.assertNotIn("路人甲", names)
        thread_ids = {item["id"] for item in ctx.plot_threads}
        self.assertIn("thread.sword", thread_ids)
        self.assertNotIn("thread.unrelated", thread_ids)
        bodies = [item.body_excerpt for item in ctx.recent_chapters]
        self.assertTrue(any("XYZ" in text for text in bodies))
        self.assertFalse(any("这一章很长" in text for text in bodies))

    def test_updater_merges_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            repo = seed_book(tmp)
            store = JsonMemoryStore(repo, "demo")
            updater = MemoryUpdater(store, max_major_events=5, max_open_threads=10)
            updater.sync_from_knowledge(
                world=repo.load_world("demo"),
                characters=repo.load_characters("demo"),
                architecture={"protagonist_arc": "从不敢拔剑到当众接剑"},
                story_seed="种子",
            )
            memory = updater.apply(
                1,
                {
                    "summary": "陆沉反击",
                    "events": [{"event_name": "演武场反击", "participants": ["knowledge.character.0001"]}],
                    "character_changes": [
                        {"id": "knowledge.character.0001", "note": "旧伤加重", "location": "演武场"}
                    ],
                    "new_facts": ["陆沉当众使出完整青岚剑诀"],
                    "unresolved_threads": [{"id": "thread.a", "text": "执事注意他", "related_ids": ["knowledge.character.0001"]}],
                    "current_conflict": "外门资格",
                    "current_tasks": ["活过追查"],
                },
            )
            self.assertEqual(memory.entities.characters["knowledge.character.0001"].location, "演武场")
            self.assertIn("陆沉当众使出完整青岚剑诀", memory.canon.facts)
            self.assertEqual(memory.plot.current_conflict, "外门资格")
            self.assertEqual(store.load_chapter_memories()[0].summary, "陆沉反击")
            memory = updater.apply(
                2,
                {
                    "summary": "追查开始",
                    "events": [{"event_name": "执事问话"}],
                    "resolved_threads": [{"id": "thread.a", "text": "执事注意他"}],
                    "unresolved_threads": [{"id": "thread.b", "text": "禁术代价"}],
                },
            )
            open_ids = {item.id for item in memory.plot.open_threads}
            self.assertNotIn("thread.a", open_ids)
            self.assertIn("thread.b", open_ids)
            self.assertEqual(len(memory.plot.closed_threads), 1)

    def test_sqlite_store(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            repo = seed_book(tmp)
            store = SqliteMemoryStore(repo, "demo")
            memory = store.load()
            memory.canon.facts.append("sqlite-fact")
            store.save(memory)
            store.save_chapter_memory(ChapterMemory(ch_no=1, summary="s1"))
            loaded = build_store("sqlite", repo, "demo").load()
            self.assertIn("sqlite-fact", loaded.canon.facts)
            self.assertEqual(store.load_chapter_memories(last_n=1)[0].summary, "s1")

    def test_unknown_backend_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = seed_book(Path(raw))
            with self.assertRaises(MemoryError):
                build_store("chroma", repo, "demo")

    def test_workflow_persists_layered_memory(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            seed_book(tmp)
            SimpleWorkflow(settings_for(tmp), "demo").run()
            self.assertTrue((tmp / "demo" / "memory" / "canon.json").exists())
            self.assertTrue((tmp / "demo" / "memory" / "entities.json").exists())
            self.assertTrue((tmp / "demo" / "memory" / "plot.json").exists())
            self.assertTrue((tmp / "demo" / "memory" / "chapters.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
