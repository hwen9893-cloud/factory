"""Memory agent: extract structured residue, then MemoryUpdater merges and persists."""

from __future__ import annotations

from typing import Any

from factory.agents.base import BaseAgent
from factory.schema.models import Character, PlotThread
from factory.schema.store import SchemaStore

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
    """Memory Extractor. Does not write prose; MemoryUpdater owns the merge."""

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
        memory = self.updater.apply(ch_no, update)
        self.context.apply_memory(memory, self.memory_store.load_chapter_memories())
        _persist_schema(self.repo, self.context.book_id, ch_no, update)
        return {"memory_update": update, "ch_no": ch_no}


def _persist_schema(repo: Any, book_id: str, ch_no: int, update: dict[str, Any]) -> None:
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
