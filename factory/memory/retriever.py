"""Select a bounded WriterContext. Never concatenates the full chapter archive."""

from __future__ import annotations

import re
from typing import Any

from factory.memory.store import MemoryStore
from factory.memory.types import (
    CharacterEntity,
    PlotThread,
    RecentChapter,
    StoryMemory,
    WriterContext,
)
from factory.storage import BookRepository

_TOKEN = re.compile(r"[\w\u4e00-\u9fff]{2,}")


class MemoryRetriever:
    """Keyword + id retrieval. Never concatenates the full chapter archive."""

    def __init__(
        self,
        store: MemoryStore,
        repo: BookRepository,
        book_id: str,
        *,
        recent_chapters: int = 3,
        prev_tail_chars: int = 400,
        max_relevant_characters: int = 8,
        max_open_threads: int = 12,
    ) -> None:
        self.store = store
        self.repo = repo
        self.book_id = book_id
        self.recent_chapters = recent_chapters
        self.prev_tail_chars = prev_tail_chars
        self.max_relevant_characters = max_relevant_characters
        self.max_open_threads = max_open_threads

    def for_writer(
        self,
        ch_no: int,
        *,
        chapter_plan: dict[str, Any] | None = None,
        volume_plan: dict[str, Any] | None = None,
        outline_chapter: dict[str, Any] | None = None,
        query_text: str = "",
    ) -> WriterContext:
        memory = self.store.load()
        hints = _hint_blob(chapter_plan, outline_chapter, query_text)
        characters = self._relevant_characters(memory, hints, chapter_plan, outline_chapter)
        threads = self._relevant_threads(memory, hints, {item.get("id") for item in characters})
        recent = self._recent_window(ch_no)
        volume = _volume_slice(volume_plan, ch_no)
        return WriterContext(
            canon=memory.canon,
            characters=characters[: self.max_relevant_characters],
            plot_threads=[item.to_dict() for item in threads[: self.max_open_threads]],
            volume=volume,
            chapter_plan=chapter_plan or outline_chapter or {},
            recent_chapters=recent,
            current_conflict=memory.plot.current_conflict,
            current_tasks=list(memory.plot.current_tasks),
            recent_events=list(memory.plot.major_events[-8:]),
        )

    def _relevant_characters(
        self,
        memory: StoryMemory,
        hints: str,
        plan: dict[str, Any] | None,
        outline: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        wanted = _character_ids(plan) | _character_ids(outline)
        tokens = set(_TOKEN.findall(hints.lower()))
        picked: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(entity: CharacterEntity) -> None:
            if entity.id in seen:
                return
            seen.add(entity.id)
            picked.append(entity.to_dict())

        protagonist = memory.canon.protagonist or {}
        proto_id = str(protagonist.get("id") or "")
        if proto_id and proto_id in memory.entities.characters:
            add(memory.entities.characters[proto_id])
        elif memory.entities.characters:
            add(next(iter(memory.entities.characters.values())))

        for cid in wanted:
            entity = memory.entities.characters.get(cid)
            if entity:
                add(entity)

        for entity in memory.entities.characters.values():
            if entity.id in seen:
                continue
            name = entity.name.lower()
            if entity.id in hints or (name and name in hints.lower()):
                add(entity)
                continue
            if tokens & set(_TOKEN.findall(name)):
                add(entity)

        return picked

    def _relevant_threads(
        self,
        memory: StoryMemory,
        hints: str,
        character_ids: set[Any],
    ) -> list[PlotThread]:
        ids = {str(item) for item in character_ids if item}
        tokens = set(_TOKEN.findall(hints.lower()))
        ranked: list[PlotThread] = []
        for thread in memory.plot.open_threads:
            related = {str(item) for item in thread.related_ids}
            text = thread.text.lower()
            if related & ids or thread.id in hints or any(token in text for token in tokens if len(token) > 1):
                ranked.append(thread)
        if not ranked:
            ranked = list(memory.plot.open_threads[-self.max_open_threads :])
        return ranked

    def _recent_window(self, ch_no: int) -> list[RecentChapter]:
        records = self.store.load_chapter_memories(last_n=self.recent_chapters)
        records = [item for item in records if item.ch_no < ch_no][-self.recent_chapters :]
        by_no = {item.ch_no: item for item in records}
        window: list[RecentChapter] = []
        start = max(1, ch_no - self.recent_chapters)
        for number in range(start, ch_no):
            memory = by_no.get(number)
            excerpt = ""
            if number == ch_no - 1:
                chapter = self.repo.load_final(self.book_id, number) or self.repo.load_draft(self.book_id, number)
                if chapter:
                    excerpt = str(chapter.get("body") or "")[-self.prev_tail_chars :]
            window.append(
                RecentChapter(
                    ch_no=number,
                    summary=(memory.summary if memory else ""),
                    body_excerpt=excerpt,
                )
            )
        return window


def _character_ids(payload: dict[str, Any] | None) -> set[str]:
    ids: set[str] = set()
    if not payload:
        return ids
    for key in ("char_focus", "present_chars"):
        for item in payload.get(key) or []:
            ids.add(str(item))
    if payload.get("pov_char"):
        ids.add(str(payload["pov_char"]))
    for scene in payload.get("scenes") or []:
        if scene.get("pov_char"):
            ids.add(str(scene["pov_char"]))
        for item in scene.get("present_chars") or []:
            ids.add(str(item))
    return ids


def _hint_blob(*parts: Any) -> str:
    chunks: list[str] = []
    for part in parts:
        if isinstance(part, dict):
            chunks.append(str(part))
        elif part:
            chunks.append(str(part))
    return "\n".join(chunks)


def _volume_slice(volume_plan: dict[str, Any] | None, ch_no: int) -> dict[str, Any]:
    if not volume_plan:
        return {}
    chapter = None
    for item in volume_plan.get("chapters") or []:
        if int(item.get("ch_no") or 0) == ch_no:
            chapter = item
            break
    return {
        "volume_no": volume_plan.get("volume_no"),
        "title": volume_plan.get("title"),
        "theme": volume_plan.get("theme"),
        "chapter": chapter or {},
    }
