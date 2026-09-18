"""Memory agent: extract a StoryStateDelta; it never mutates persistent state."""

from __future__ import annotations

from typing import Any

from factory.agents.base import BaseAgent
import hashlib

from factory.schema.contracts import EntityChange, StoryStateDelta
from factory.state import StoryStateRepository

MEMORY_SCHEMA = {
    "type": "object",
    "required": ["summary"],
    "properties": {
        "summary": {"type": "string"},
        "events": {"type": "array"},
        "character_changes": {"type": "array"},
        "new_facts": {"type": "array"},
        "unresolved_threads": {"type": "array"},
        "resolved_threads": {"type": "array"},
        "current_conflict": {"type": "string"},
        "current_tasks": {"type": "array"},
        "timeline_events": {"type": "array"},
        "character_state": {"type": "array"},
        "facts": {"type": "array"},
    },
}


class MemoryAgent(BaseAgent):
    """Memory extractor. AtomicFinalizer owns every persistent mutation."""

    name = "memory"
    model = "reviewer"
    prompt_name = "memory_extract"
    temperature = 0.2
    max_retries = 1
    required_outputs = ("memory_update",)
    output_schema = MEMORY_SCHEMA

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        ch_no = int(state.get("ch_no") or self.context.current_chapter)
        _title, body = self.chapter_text(state, ch_no)
        chapter_plan = state.get("chapter_plan") or self.repo.load_chapter_plan(self.context.book_id, ch_no) or {}
        extra = self.retrieved_vars(state, ch_no, chapter_plan=chapter_plan, query_text=body[:800])
        extra.update({"body": body, "ch_no": ch_no, "chapter_plan": chapter_plan})
        update = self.ask_json(purpose="memory", extra_vars=extra)
        current = StoryStateRepository(self.repo, self.context.book_id).load()
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
        operation_id = f"chapter.{ch_no:06d}.{digest}"
        raw_changes = list(update.get("character_changes") or update.get("character_state") or [])
        changes = []
        for raw in raw_changes:
            if not isinstance(raw, dict) or not raw.get("id"):
                continue
            patch = {key: value for key, value in raw.items() if key not in {"id"} and value not in (None, "")}
            changes.append(EntityChange(id=str(raw["id"]), patch=patch))
        resolved = []
        for item in update.get("resolved_threads") or []:
            if isinstance(item, dict):
                resolved.append(str(item.get("id") or item.get("text") or item.get("summary") or ""))
            else:
                resolved.append(str(item))
        delta = StoryStateDelta(
            operation_id=operation_id,
            chapter_no=ch_no,
            base_state_version=current.state_version,
            character_changes=changes,
            relationship_changes=list((update.get("entity_updates") or {}).get("relationships") or []),
            timeline_events=list(update.get("events") or update.get("timeline_events") or []),
            new_facts=[str(item) for item in (update.get("new_facts") or update.get("facts") or [])],
            new_threads=[_as_mapping(item) for item in (update.get("unresolved_threads") or [])],
            resolved_threads=[item for item in resolved if item],
            knowledge_changes=list(update.get("knowledge_changes") or []),
            foreshadowing_changes=list(update.get("foreshadowing_changes") or []),
        )
        return {
            "memory_update": update,
            "story_state_delta": delta.model_dump(mode="json"),
            "ch_no": ch_no,
        }


def persist_legacy_projection(repo: Any, book_id: str, ch_no: int, update: dict[str, Any]) -> None:
    """Compatibility projection, invoked inside AtomicFinalizer's rollback boundary."""
    from factory.schema.models import Character, PlotThread
    from factory.schema.store import SchemaStore

    store = SchemaStore(repo, book_id)
    for raw in update.get("unresolved_threads") or []:
        payload = _as_mapping(raw)
        payload.setdefault("setup_chapter", ch_no)
        payload.setdefault("status", "open")
        store.upsert_plot_thread(PlotThread.model_validate(payload))
    for raw in update.get("resolved_threads") or []:
        payload = _as_mapping(raw)
        payload["status"] = "resolved"
        payload.setdefault("payoff_chapter", ch_no)
        store.upsert_plot_thread(PlotThread.model_validate(payload))
    for change in update.get("character_changes") or update.get("character_state") or []:
        if not isinstance(change, dict) or not change.get("id"):
            continue
        store.update_character(str(change["id"]), Character.model_validate({"name": change.get("name") or change["id"], **change}))


def _as_mapping(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    return {"title": str(raw)}
