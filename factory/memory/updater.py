"""Merge extracted chapter memory into StoryMemory and persist it."""

from __future__ import annotations

from typing import Any

from factory.memory.store import MemoryStore
from factory.memory.types import (
    ChapterMemory,
    CharacterEntity,
    EntityState,
    GlobalCanon,
    PlotMemory,
    PlotThread,
    StoryMemory,
)


def canon_from_knowledge(
    *,
    world: dict[str, Any],
    characters: list[dict[str, Any]],
    architecture: dict[str, Any],
    story_seed: str = "",
    extra_facts: list[str] | None = None,
) -> GlobalCanon:
    protagonist = dict(characters[0]) if characters else {}
    majors = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "status": item.get("status", "alive"),
            "goal": item.get("goal"),
        }
        for item in characters[:6]
    ]
    goals = [item for item in (architecture.get("protagonist_arc"), architecture.get("premise")) if item]
    if story_seed and story_seed not in goals:
        goals.append(story_seed)
    return GlobalCanon(
        world_summary=str(world.get("summary") or ""),
        rules=[str(item) for item in (world.get("rules") or [])],
        protagonist=protagonist,
        major_characters=majors,
        core_setting={
            "realms": world.get("realms") or [],
            "sects": world.get("sects") or [],
            "places": world.get("places") or [],
        },
        main_goals=[str(item) for item in goals],
        facts=list(extra_facts or []),
    )


def entities_from_knowledge(
    characters: list[dict[str, Any]],
    legacy_state: list[dict[str, Any]] | None = None,
) -> EntityState:
    entities = EntityState()
    by_id = {str(item.get("id")): dict(item) for item in (legacy_state or []) if item.get("id")}
    for item in characters:
        cid = str(item.get("id") or "")
        if not cid:
            continue
        overlay = by_id.get(cid, {})
        merged = {
            **item,
            **{key: value for key, value in overlay.items() if value not in (None, "")},
            "id": cid,
            "realm": overlay.get("realm") or item.get("cultivation_realm") or item.get("realm") or "",
            "faction": overlay.get("faction") or item.get("faction") or item.get("sect") or "",
            "skills": overlay.get("skills") or item.get("skills") or item.get("techniques") or [],
            "items": overlay.get("items")
            or [ref.get("name") if isinstance(ref, dict) else str(ref) for ref in (item.get("inventory") or item.get("weapons") or [])],
        }
        entities.characters[cid] = CharacterEntity.from_dict(merged)
    for cid, overlay in by_id.items():
        if cid not in entities.characters:
            entities.characters[cid] = CharacterEntity.from_dict(overlay)
    return entities


class MemoryUpdater:
    """Chapter → structured extraction → merge → persist. Does not call models."""

    def __init__(self, store: MemoryStore, *, max_major_events: int = 40, max_open_threads: int = 20) -> None:
        self.store = store
        self.max_major_events = max_major_events
        self.max_open_threads = max_open_threads

    def sync_from_knowledge(
        self,
        *,
        world: dict[str, Any],
        characters: list[dict[str, Any]],
        architecture: dict[str, Any],
        story_seed: str = "",
    ) -> StoryMemory:
        memory = self.store.load()
        facts = list(memory.canon.facts)
        memory.canon = canon_from_knowledge(
            world=world,
            characters=characters,
            architecture=architecture,
            story_seed=story_seed,
            extra_facts=facts,
        )
        merged = entities_from_knowledge(characters, memory.entities.character_list())
        for cid, entity in memory.entities.characters.items():
            if cid in merged.characters:
                base = merged.characters[cid].to_dict()
                overlay = {key: value for key, value in entity.to_dict().items() if value not in (None, "", [])}
                merged.characters[cid] = CharacterEntity.from_dict({**base, **overlay})
        memory.entities.characters = merged.characters
        if not memory.plot.long_term_goals and architecture.get("protagonist_arc"):
            memory.plot.long_term_goals = [str(architecture["protagonist_arc"])]
        self.store.save(memory)
        return memory

    def apply(self, ch_no: int, extraction: dict[str, Any]) -> StoryMemory:
        memory = self.store.load()
        record = chapter_memory_from_extraction(ch_no, extraction)
        self.store.save_chapter_memory(record)
        _merge_canon_facts(memory.canon, record.new_facts)
        _merge_entities(memory.entities, extraction, record.character_changes)
        _merge_plot(memory.plot, extraction, record, self.max_major_events, self.max_open_threads)
        self.store.save(memory)
        return memory


def chapter_memory_from_extraction(ch_no: int, extraction: dict[str, Any]) -> ChapterMemory:
    events = list(extraction.get("events") or extraction.get("timeline_events") or [])
    changes = list(extraction.get("character_changes") or [])
    if not changes and extraction.get("character_state"):
        changes = [{"id": item.get("id"), "name": item.get("name"), "note": item.get("note")} for item in extraction["character_state"]]
    facts = [str(item) for item in (extraction.get("new_facts") or extraction.get("facts") or [])]
    threads = list(extraction.get("unresolved_threads") or [])
    return ChapterMemory(
        ch_no=ch_no,
        summary=str(extraction.get("summary") or ""),
        events=events,
        character_changes=changes,
        new_facts=facts,
        unresolved_threads=threads,
    )


def _merge_canon_facts(canon: GlobalCanon, facts: list[str]) -> None:
    existing = set(canon.facts)
    for fact in facts:
        if fact and fact not in existing:
            canon.facts.append(fact)
            existing.add(fact)
    canon.facts = canon.facts[-80:]


def _merge_entities(
    entities: EntityState,
    extraction: dict[str, Any],
    changes: list[dict[str, Any]],
) -> None:
    for item in extraction.get("character_state") or []:
        _upsert_character(entities, item)
    for item in changes:
        _upsert_character(entities, item)
    for item in (extraction.get("entity_updates") or {}).get("characters") or []:
        _upsert_character(entities, item)
    for rel in (extraction.get("entity_updates") or {}).get("relationships") or []:
        if rel and rel not in entities.relationships:
            entities.relationships.append(rel)
    for item in (extraction.get("entity_updates") or {}).get("items") or []:
        if item and item not in entities.items:
            entities.items.append(item)


def _upsert_character(entities: EntityState, item: dict[str, Any]) -> None:
    cid = str(item.get("id") or "")
    if not cid:
        return
    current = entities.characters.get(cid, CharacterEntity(id=cid, name=str(item.get("name") or cid)))
    patch = {key: value for key, value in item.items() if value not in (None, "", [])}
    if item.get("note") and current.note and item["note"] not in current.note:
        patch["note"] = f"{current.note}；{item['note']}"
    entities.characters[cid] = CharacterEntity.from_dict({**current.to_dict(), **patch, "id": cid})


def _merge_plot(
    plot: PlotMemory,
    extraction: dict[str, Any],
    record: ChapterMemory,
    max_events: int,
    max_open: int,
) -> None:
    for event in record.events:
        payload = event if isinstance(event, dict) else {"event_name": str(event), "chapter_no": record.ch_no}
        payload.setdefault("chapter_no", record.ch_no)
        plot.major_events.append(payload)
    plot.major_events = plot.major_events[-max_events:]
    if extraction.get("current_conflict"):
        plot.current_conflict = str(extraction["current_conflict"])
    if extraction.get("current_tasks"):
        plot.current_tasks = [str(item) for item in extraction["current_tasks"]]
    for raw in record.unresolved_threads:
        thread = _as_thread(raw, record.ch_no, "open")
        if thread and not _has_thread(plot.open_threads, thread):
            plot.open_threads.append(thread)
    for raw in extraction.get("resolved_threads") or []:
        thread = _as_thread(raw, record.ch_no, "closed")
        if not thread:
            continue
        plot.open_threads = [item for item in plot.open_threads if item.id != thread.id and item.text != thread.text]
        thread.status = "closed"
        if not _has_thread(plot.closed_threads, thread):
            plot.closed_threads.append(thread)
    plot.open_threads = plot.open_threads[-max_open:]
    plot.closed_threads = plot.closed_threads[-max_open:]


def _as_thread(raw: Any, ch_no: int, status: str) -> PlotThread | None:
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        return PlotThread(id=f"thread.{ch_no}.{text[:12]}", text=text, status=status, chapter_no=ch_no)
    if isinstance(raw, dict):
        text = str(raw.get("text") or raw.get("summary") or "")
        if not text:
            return None
        related = raw.get("related_ids") or raw.get("participants") or []
        return PlotThread(
            id=str(raw.get("id") or f"thread.{ch_no}.{text[:12]}"),
            text=text,
            status=status,
            related_ids=[str(item) for item in related],
            chapter_no=int(raw.get("chapter_no") or ch_no),
        )
    return None


def _has_thread(rows: list[PlotThread], thread: PlotThread) -> bool:
    return any(item.id == thread.id or item.text == thread.text for item in rows)
