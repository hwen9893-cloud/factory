"""Scene planner expands ChapterIntent without writing prose."""

from __future__ import annotations

from typing import Any

from factory.agents.base import BaseAgent
from factory.pipeline.models import ChapterIntent, ScenePlan
from factory.pipeline.validators import SceneCoverageValidator

SCENE_PLAN_SCHEMA = {
    "type": "object",
    "required": ["scenes"],
    "properties": {"scenes": {"type": "array", "items": ScenePlan.model_json_schema()}},
}


class ScenePlannerAgent(BaseAgent):
    name = "scene_planner"
    model = "planner"
    prompt_name = "scene_planner"
    temperature = 0.35
    required_outputs = ("scene_plan",)
    output_schema = SCENE_PLAN_SCHEMA

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        ch_no = int(state.get("ch_no") or self.context.current_chapter)
        raw_intent = state.get("chapter_intent") or (state.get("chapter_plan") or {}).get("intent") or state.get("chapter_plan")
        if not raw_intent:
            raise ValueError("no ChapterIntent; run chapter_planner first")
        intent = ChapterIntent.model_validate(raw_intent)
        result = self.ask_json(
            purpose="scene_plan",
            extra_vars={"chapter_intent": intent.model_dump(mode="json"), "ch_no": ch_no},
        )
        scenes = [ScenePlan.model_validate(item) for item in result.get("scenes") or []]
        coverage = SceneCoverageValidator().validate(intent, scenes)
        if not coverage.valid:
            from factory.agents.base import SchemaValidationError

            raise SchemaValidationError("; ".join(coverage.issues))
        return {"scene_plan": [item.model_dump(mode="json") for item in scenes], "chapter_intent": intent.model_dump(mode="json"), "ch_no": ch_no}

