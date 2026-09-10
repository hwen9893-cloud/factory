"""Story-structure agents: architecture, book outline, volume plan. No chapter prose."""

from __future__ import annotations

from typing import Any

from factory.agents.base import BaseAgent

ARCHITECT_SCHEMA = {
    "type": "object",
    "required": ["title", "premise", "theme", "protagonist_arc", "volume_beats"],
    "properties": {
        "title": {"type": "string"},
        "premise": {"type": "string"},
        "theme": {"type": "string"},
        "tone": {"type": "string"},
        "protagonist_arc": {"type": "string"},
        "volume_beats": {"type": "array"},
    },
}

OUTLINE_SCHEMA = {
    "type": "object",
    "required": ["title", "premise", "volumes"],
    "properties": {
        "title": {"type": "string"},
        "premise": {"type": "string"},
        "volumes": {"type": "array"},
    },
}

VOLUME_SCHEMA = {
    "type": "object",
    "required": ["volume_no", "title", "chapters"],
    "properties": {
        "volume_no": {"type": "integer"},
        "title": {"type": "string"},
        "theme": {"type": "string"},
        "chapters": {"type": "array"},
    },
}


class NovelArchitectAgent(BaseAgent):
    """Decide story spine: theme, arcs, volume beats. Does not list every chapter."""

    name = "novel_architect"
    model = "architect"
    prompt_name = "architect"
    temperature = 0.45
    required_inputs = ("story_seed",)
    required_outputs = ("architecture",)
    output_schema = ARCHITECT_SCHEMA

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        architecture = self.ask_json(purpose="architect")
        if architecture.get("title"):
            self.context.title = str(architecture["title"])
        self.context.architecture = architecture
        self.repo.save_architecture(self.context.book_id, architecture)
        self.context.save_meta(self.repo)
        self._sync_canon()
        return {"architecture": architecture}


class OutlineAgent(BaseAgent):
    """Expand architecture into a chapter-level event list per volume."""

    name = "outline"
    model = "planner"
    prompt_name = "outline"
    temperature = 0.4
    required_inputs = ("story_seed",)
    required_outputs = ("outline",)
    output_schema = OUTLINE_SCHEMA

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        outline = self.ask_json(purpose="outline")
        if outline.get("title"):
            self.context.title = str(outline["title"])
        self.context.outline = outline
        self.repo.save_outline(self.context.book_id, outline)
        self.context.save_meta(self.repo)
        return {"outline": outline}


class VolumePlannerAgent(BaseAgent):
    """Turn the current volume's outline slice into pacing, functions, and ending states."""

    name = "volume_planner"
    model = "planner"
    prompt_name = "volume_planner"
    temperature = 0.4
    required_outputs = ("volume_plan",)
    output_schema = VOLUME_SCHEMA

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if not self.context.outline:
            raise ValueError("no outline; run outline agent first")
        volume_no = int(state.get("volume_no") or self.context.current_volume)
        plan = self.ask_json(purpose="volume_plan", extra_vars={"volume_no": volume_no})
        plan["volume_no"] = volume_no
        self.context.volume_plan = plan
        self.repo.save_volume_plan(self.context.book_id, volume_no, plan)
        return {"volume_plan": plan, "volume_no": volume_no}
