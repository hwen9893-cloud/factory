"""Persistence backends. Default is JSON files. SQLite is optional."""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from factory.memory.types import ChapterMemory, StoryMemory
from factory.storage import BookRepository


class MemoryError(RuntimeError):
    """Store failure."""


class MemoryStore(ABC):
    """Read/write Levels 1–4. Implementations must not load every chapter body."""

    @abstractmethod
    def load(self) -> StoryMemory:
        """Load canon, entities, and plot."""

    @abstractmethod
    def save(self, memory: StoryMemory) -> None:
        """Persist Levels 1–3."""

    @abstractmethod
    def save_chapter_memory(self, record: ChapterMemory) -> None:
        """Upsert one Level-4 record."""

    @abstractmethod
    def load_chapter_memories(self, *, last_n: int | None = None) -> list[ChapterMemory]:
        """Return chapter memories, oldest first. last_n=None means all (summaries only)."""


class JsonMemoryStore(MemoryStore):
    """Default backend: memory/canon.json, entities.json, plot.json, chapters.jsonl."""

    def __init__(self, repo: BookRepository, book_id: str) -> None:
        self.repo = repo
        self.book_id = book_id
        self.root = repo.book_dir(book_id) / "memory"
        self.root.mkdir(parents=True, exist_ok=True)

    def load(self) -> StoryMemory:
        canon_path = self.root / "canon.json"
        if not canon_path.exists():
            memory = hydrate_from_knowledge(self.repo, self.book_id)
            self.save(memory)
            return memory
        return StoryMemory.from_dict(
            {
                "canon": _read_json(canon_path, {}),
                "entities": _read_json(self.root / "entities.json", {}),
                "plot": _read_json(self.root / "plot.json", {}),
            }
        )

    def save(self, memory: StoryMemory) -> None:
        payload = memory.to_dict()
        (self.root / "canon.json").write_text(_dump(payload["canon"]), encoding="utf-8")
        (self.root / "entities.json").write_text(_dump(payload["entities"]), encoding="utf-8")
        (self.root / "plot.json").write_text(_dump(payload["plot"]), encoding="utf-8")
        self._mirror_legacy(memory)

    def save_chapter_memory(self, record: ChapterMemory) -> None:
        rows = {item.ch_no: item for item in self.load_chapter_memories()}
        rows[record.ch_no] = record
        path = self.root / "chapters.jsonl"
        lines = [
            json.dumps(rows[ch_no].to_dict(), ensure_ascii=False)
            for ch_no in sorted(rows)
        ]
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        summaries = self.root / "summaries.jsonl"
        summaries.write_text(
            "".join(
                json.dumps({"ch_no": item.ch_no, "summary": item.summary}, ensure_ascii=False) + "\n"
                for item in (rows[key] for key in sorted(rows))
                if item.summary
            ),
            encoding="utf-8",
        )

    def load_chapter_memories(self, *, last_n: int | None = None) -> list[ChapterMemory]:
        path = self.root / "chapters.jsonl"
        rows: list[ChapterMemory] = []
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(ChapterMemory.from_dict(json.loads(line)))
        if not rows:
            rows = _legacy_summaries(self.root / "summaries.jsonl")
        rows.sort(key=lambda item: item.ch_no)
        if last_n is not None:
            return rows[-last_n:]
        return rows

    def _mirror_legacy(self, memory: StoryMemory) -> None:
        """Keep old files in sync so existing readers keep working."""
        states = memory.entities.character_list()
        (self.root / "character_state.json").write_text(_dump(states), encoding="utf-8")
        (self.root / "notes.json").write_text(_dump({"facts": memory.canon.facts}), encoding="utf-8")


class SqliteMemoryStore(MemoryStore):
    """Same document as JSON, stored in memory/story.sqlite. Stdlib only."""

    def __init__(self, repo: BookRepository, book_id: str) -> None:
        self.repo = repo
        self.book_id = book_id
        self.root = repo.book_dir(book_id) / "memory"
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "story.sqlite"
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, json TEXT NOT NULL)")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS chapter_memory (ch_no INTEGER PRIMARY KEY, json TEXT NOT NULL)"
            )

    def load(self) -> StoryMemory:
        with self._connect() as conn:
            rows = {key: json.loads(blob) for key, blob in conn.execute("SELECT key, json FROM kv")}
        if "canon" not in rows:
            memory = hydrate_from_knowledge(self.repo, self.book_id)
            self.save(memory)
            return memory
        return StoryMemory.from_dict(
            {"canon": rows.get("canon"), "entities": rows.get("entities"), "plot": rows.get("plot")}
        )

    def save(self, memory: StoryMemory) -> None:
        payload = memory.to_dict()
        with self._connect() as conn:
            for key in ("canon", "entities", "plot"):
                conn.execute(
                    "INSERT INTO kv(key, json) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET json=excluded.json",
                    (key, json.dumps(payload[key], ensure_ascii=False)),
                )

    def save_chapter_memory(self, record: ChapterMemory) -> None:
        blob = json.dumps(record.to_dict(), ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO chapter_memory(ch_no, json) VALUES(?, ?) ON CONFLICT(ch_no) DO UPDATE SET json=excluded.json",
                (record.ch_no, blob),
            )

    def load_chapter_memories(self, *, last_n: int | None = None) -> list[ChapterMemory]:
        sql = "SELECT json FROM chapter_memory ORDER BY ch_no"
        if last_n is not None:
            sql = "SELECT json FROM chapter_memory ORDER BY ch_no DESC LIMIT ?"
        with self._connect() as conn:
            if last_n is not None:
                blobs = [row[0] for row in conn.execute(sql, (last_n,))]
                rows = [ChapterMemory.from_dict(json.loads(blob)) for blob in blobs]
                rows.sort(key=lambda item: item.ch_no)
                return rows
            return [ChapterMemory.from_dict(json.loads(row[0])) for row in conn.execute(sql)]


def hydrate_from_knowledge(repo: BookRepository, book_id: str) -> StoryMemory:
    """Build Levels 1–2 from world/character files so old books don't need a migration."""
    from factory.memory.updater import canon_from_knowledge, entities_from_knowledge

    world = repo.load_world(book_id)
    characters = repo.load_characters(book_id)
    architecture = repo.load_architecture(book_id) or {}
    meta = repo.load_meta(book_id)
    notes = repo.load_notes(book_id)
    legacy_state = repo.load_character_state(book_id)
    timeline = repo.load_timeline(book_id)
    memory = StoryMemory(
        canon=canon_from_knowledge(
            world=world,
            characters=characters,
            architecture=architecture,
            story_seed=str(meta.get("story_seed") or ""),
            extra_facts=list(notes.get("facts") or []),
        ),
        entities=entities_from_knowledge(characters, legacy_state),
    )
    events = []
    for item in timeline:
        if isinstance(item, dict):
            events.append(item)
    memory.plot.major_events = events[-40:]
    if architecture.get("protagonist_arc"):
        memory.plot.long_term_goals = [str(architecture["protagonist_arc"])]
    return memory


def build_store(backend: str, repo: BookRepository, book_id: str) -> MemoryStore:
    name = (backend or "json").strip().lower()
    if name in {"json", "yaml", "file"}:
        return JsonMemoryStore(repo, book_id)
    if name == "sqlite":
        return SqliteMemoryStore(repo, book_id)
    raise MemoryError(f"unknown memory backend {backend!r}; use json or sqlite")


def _dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _legacy_summaries(path: Path) -> list[ChapterMemory]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        rows.append(ChapterMemory(ch_no=int(item.get("ch_no") or 0), summary=str(item.get("summary") or "")))
    return rows
