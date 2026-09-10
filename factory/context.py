"""StoryContext is the in-memory view of one book. Agents read this, not raw files."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from factory.storage import BookRepository


@dataclass
class StoryContext:
    """Single snapshot: metadata, setting, outline, current position, recent text, memory."""

    book_id: str
    title: str = ""
    genre: str = ""
    style: str = ""
    story_seed: str = ""
    world: dict[str, Any] = field(default_factory=dict)
    characters: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    outline: dict[str, Any] | None = None
    architecture: dict[str, Any] | None = None
    volume_plan: dict[str, Any] | None = None
    character_state: list[dict[str, Any]] = field(default_factory=list)
    current_volume: int = 1
    current_chapter: int = 1
    target_chapters: int = 3
    recent_chapters: list[dict[str, Any]] = field(default_factory=list)
    long_term_memory: dict[str, Any] = field(default_factory=dict)
    summaries: list[dict[str, Any]] = field(default_factory=list)
    prev_tail_chars: int = 400
    language: str = "zh-CN"
    chapter_target_words: int = 5000

    @classmethod
    def load(cls, repo: BookRepository, book_id: str, *, recent_limit: int = 3, prev_tail_chars: int = 400) -> StoryContext:
        meta = repo.load_meta(book_id)
        current_chapter = int(meta.get("current_chapter", 1))
        current_volume = int(meta.get("current_volume", 1))
        return cls(
            book_id=book_id,
            title=str(meta.get("title") or book_id),
            genre=str(meta.get("genre") or ""),
            style=str(meta.get("style") or ""),
            story_seed=str(meta.get("story_seed") or ""),
            world=repo.load_world(book_id),
            characters=repo.load_characters(book_id),
            timeline=repo.load_timeline(book_id),
            outline=repo.load_outline(book_id),
            architecture=repo.load_architecture(book_id),
            volume_plan=repo.load_volume_plan(book_id, current_volume),
            character_state=repo.load_character_state(book_id),
            current_volume=current_volume,
            current_chapter=current_chapter,
            target_chapters=int(meta.get("target_chapters", 3)),
            recent_chapters=repo.load_recent_finals(book_id, current_chapter, 1),
            long_term_memory=repo.load_notes(book_id),
            summaries=repo.load_summaries(book_id),
            prev_tail_chars=prev_tail_chars,
        )

    def save_meta(self, repo: BookRepository) -> None:
        repo.save_meta(
            self.book_id,
            {
                "book_id": self.book_id,
                "title": self.title,
                "genre": self.genre,
                "style": self.style,
                "story_seed": self.story_seed,
                "current_volume": self.current_volume,
                "current_chapter": self.current_chapter,
                "target_chapters": self.target_chapters,
            },
        )

    def apply_memory(self, memory: Any, chapter_records: list[Any] | None = None) -> None:
        """Refresh compact views from StoryMemory after load or update."""
        self.character_state = memory.entities.character_list()
        self.long_term_memory = {"facts": list(memory.canon.facts)}
        self.timeline = list(memory.plot.major_events)
        if chapter_records is not None:
            self.summaries = [
                {"ch_no": item.ch_no, "summary": item.summary} for item in chapter_records if getattr(item, "summary", "")
            ]

    def character_by_id(self, character_id: str) -> dict[str, Any] | None:
        for item in self.characters:
            if item.get("id") == character_id:
                return item
        return None

    def chapter_outline(self, ch_no: int) -> dict[str, Any] | None:
        if not self.outline:
            return None
        for volume in self.outline.get("volumes") or []:
            for chapter in volume.get("chapters") or []:
                if int(chapter.get("ch_no", 0)) == ch_no:
                    return chapter
        return None

    def prev_tail(self) -> str:
        if not self.recent_chapters:
            return ""
        body = str(self.recent_chapters[-1].get("body") or "")
        return body[-self.prev_tail_chars :]

    def recent_summary_text(self) -> str:
        rows = self.summaries[-3:]
        if not rows:
            return "（无）"
        return "\n".join(f"第{row.get('ch_no')}章：{row.get('summary')}" for row in rows)

    def recent_context_text(self) -> str:
        tail = self.prev_tail() or "（本书开头）"
        return f"{self.recent_summary_text()}\n\n上章文末：\n{tail}"

    def outlined_chapters(self) -> list[int]:
        numbers: list[int] = []
        for volume in (self.outline or {}).get("volumes") or []:
            for chapter in volume.get("chapters") or []:
                ch_no = int(chapter.get("ch_no") or 0)
                if ch_no:
                    numbers.append(ch_no)
        return sorted(numbers)

    def volume_for_chapter(self, ch_no: int) -> int:
        for volume in (self.outline or {}).get("volumes") or []:
            for chapter in volume.get("chapters") or []:
                if int(chapter.get("ch_no") or 0) == ch_no:
                    return int(volume.get("volume_no") or self.current_volume)
        return self.current_volume

    def volume_chapter(self, ch_no: int) -> dict[str, Any] | None:
        if not self.volume_plan:
            return None
        for chapter in self.volume_plan.get("chapters") or []:
            if int(chapter.get("ch_no", 0)) == ch_no:
                return chapter
        return None

    def prompt_vars(self) -> dict[str, Any]:
        """Common template variables injected into every agent prompt."""
        characters = self.character_state or self.characters
        plot = {
            "architecture": self.architecture or {},
            "outline": self.outline or {},
            "volume_plan": self.volume_plan or {},
        }
        return {
            "book_id": self.book_id,
            "title": self.title,
            "story_title": self.title,
            "genre": self.genre,
            "style": self.style,
            "story_seed": self.story_seed,
            "world": self.world,
            "world_context": self.world,
            "characters": self.characters,
            "character_context": characters,
            "character_state": characters,
            "timeline": self.timeline,
            "architecture": self.architecture or {},
            "outline": self.outline or {},
            "plot_context": plot,
            "chapter_plan": {},
            "volume_plan": self.volume_plan or {},
            "language": self.language,
            "chapter_target_words": self.chapter_target_words,
            "current_volume": self.current_volume,
            "current_chapter": self.current_chapter,
            "target_chapters": self.target_chapters,
            "prev_tail": self.prev_tail() or "（本书开头）",
            "recent_summaries": self.recent_summary_text(),
            "recent_context": self.recent_context_text(),
            "memory": self.long_term_memory,
        }
