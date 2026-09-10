"""Layered story memory. Chapter text never lives here — only compact structured state."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any


def _from_dict(cls: type, payload: dict[str, Any] | None):
    if not payload:
        return cls()
    allowed = {item.name for item in fields(cls)}
    return cls(**{key: value for key, value in payload.items() if key in allowed})


@dataclass
class GlobalCanon:
    """Level 1 — permanent facts. Always retrieved, kept small."""

    world_summary: str = ""
    rules: list[str] = field(default_factory=list)
    protagonist: dict[str, Any] = field(default_factory=dict)
    major_characters: list[dict[str, Any]] = field(default_factory=list)
    core_setting: dict[str, Any] = field(default_factory=dict)
    main_goals: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> GlobalCanon:
        return _from_dict(cls, payload)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CharacterEntity:
    """Level 2 — one person's current state."""

    id: str
    name: str
    status: str = "alive"
    realm: str = ""
    location: str = ""
    faction: str = ""
    skills: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    voice_style: str = ""
    personality: str = ""
    note: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> CharacterEntity:
        data = dict(payload or {})
        data.setdefault("id", "")
        data.setdefault("name", "")
        return _from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EntityState:
    """Level 2 — dynamic world state. Retrieved by relevance, never as a full dump to the writer."""

    characters: dict[str, CharacterEntity] = field(default_factory=dict)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)
    places: list[dict[str, Any]] = field(default_factory=list)
    factions: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> EntityState:
        raw = dict(payload or {})
        characters: dict[str, CharacterEntity] = {}
        for key, item in (raw.get("characters") or {}).items():
            entity = CharacterEntity.from_dict(item if isinstance(item, dict) else {"id": key, "name": str(item)})
            characters[entity.id or str(key)] = entity
        return cls(
            characters=characters,
            relationships=list(raw.get("relationships") or []),
            items=list(raw.get("items") or []),
            places=list(raw.get("places") or []),
            factions=list(raw.get("factions") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "characters": {key: value.to_dict() for key, value in self.characters.items()},
            "relationships": self.relationships,
            "items": self.items,
            "places": self.places,
            "factions": self.factions,
        }

    def character_list(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.characters.values()]


@dataclass
class PlotThread:
    id: str
    text: str
    status: str = "open"  # open | closed
    related_ids: list[str] = field(default_factory=list)
    chapter_no: int | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> PlotThread:
        data = dict(payload or {})
        data.setdefault("id", "")
        data.setdefault("text", str(data.get("text") or data.get("summary") or ""))
        return _from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PlotMemory:
    """Level 3 — story progress. Retriever only sends open / current slices."""

    major_events: list[dict[str, Any]] = field(default_factory=list)
    open_threads: list[PlotThread] = field(default_factory=list)
    closed_threads: list[PlotThread] = field(default_factory=list)
    current_conflict: str = ""
    current_tasks: list[str] = field(default_factory=list)
    long_term_goals: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> PlotMemory:
        raw = dict(payload or {})
        return cls(
            major_events=list(raw.get("major_events") or []),
            open_threads=[PlotThread.from_dict(item) for item in raw.get("open_threads") or []],
            closed_threads=[PlotThread.from_dict(item) for item in raw.get("closed_threads") or []],
            current_conflict=str(raw.get("current_conflict") or ""),
            current_tasks=list(raw.get("current_tasks") or []),
            long_term_goals=list(raw.get("long_term_goals") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "major_events": self.major_events,
            "open_threads": [item.to_dict() for item in self.open_threads],
            "closed_threads": [item.to_dict() for item in self.closed_threads],
            "current_conflict": self.current_conflict,
            "current_tasks": self.current_tasks,
            "long_term_goals": self.long_term_goals,
        }


@dataclass
class ChapterMemory:
    """Level 4 — one chapter's structured residue. Indexed by ch_no, not sent as a corpus."""

    ch_no: int
    summary: str = ""
    events: list[Any] = field(default_factory=list)
    character_changes: list[dict[str, Any]] = field(default_factory=list)
    new_facts: list[str] = field(default_factory=list)
    unresolved_threads: list[Any] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> ChapterMemory:
        data = dict(payload or {})
        data.setdefault("ch_no", 0)
        return _from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StoryMemory:
    """Levels 1–3 in RAM. Level 4 lives in the store; Level 5 is computed by the retriever."""

    canon: GlobalCanon = field(default_factory=GlobalCanon)
    entities: EntityState = field(default_factory=EntityState)
    plot: PlotMemory = field(default_factory=PlotMemory)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> StoryMemory:
        raw = dict(payload or {})
        return cls(
            canon=GlobalCanon.from_dict(raw.get("canon")),
            entities=EntityState.from_dict(raw.get("entities")),
            plot=PlotMemory.from_dict(raw.get("plot")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "canon": self.canon.to_dict(),
            "entities": self.entities.to_dict(),
            "plot": self.plot.to_dict(),
        }


@dataclass
class RecentChapter:
    """Level 5 — a bounded recent window. Body is optional; summary is preferred."""

    ch_no: int
    summary: str = ""
    body_excerpt: str = ""


@dataclass
class WriterContext:
    """Bounded packet the writer (and planner/continuity) may see. Never the full book."""

    canon: GlobalCanon
    characters: list[dict[str, Any]]
    plot_threads: list[dict[str, Any]]
    volume: dict[str, Any]
    chapter_plan: dict[str, Any]
    recent_chapters: list[RecentChapter]
    current_conflict: str = ""
    current_tasks: list[str] = field(default_factory=list)
    recent_events: list[dict[str, Any]] = field(default_factory=list)

    def prompt_vars(self) -> dict[str, Any]:
        prev = next((item.body_excerpt for item in reversed(self.recent_chapters) if item.body_excerpt), "")
        summaries = [
            {"ch_no": item.ch_no, "summary": item.summary, "excerpt": item.body_excerpt}
            for item in self.recent_chapters
        ]
        recent_summaries = (
            "\n".join(f"第{item.ch_no}章：{item.summary}" for item in self.recent_chapters if item.summary)
            or "（无）"
        )
        prev_tail = prev or "（本书开头）"
        canon = self.canon.to_dict()
        return {
            "canon": canon,
            "world_context": canon,
            "relevant_characters": self.characters,
            "character_context": self.characters,
            "plot_threads": self.plot_threads,
            "plot_context": self.plot_threads,
            "volume": self.volume,
            "chapter_plan": self.chapter_plan,
            "recent_chapters": summaries,
            "prev_tail": prev_tail,
            "recent_summaries": recent_summaries,
            "recent_context": f"{recent_summaries}\n\n上章文末：\n{prev_tail}",
            "current_conflict": self.current_conflict,
            "current_tasks": self.current_tasks,
            "recent_events": self.recent_events,
        }
