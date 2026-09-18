"""Chapter production: planner makes the task, writer only writes prose."""

from __future__ import annotations

from typing import Any

from factory.agents.base import BaseAgent
from factory.pipeline.models import ChapterDraft, ChapterIntent, ChapterPlan, ScenePlan


class ChapterPlannerAgent(BaseAgent):
    """Convert outline + volume plan + current story state into a concrete chapter task."""

    name = "chapter_planner"
    model = "planner"
    prompt_name = "chapter_planner"
    temperature = 0.35
    required_outputs = ("chapter_plan",)
    output_schema = ChapterIntent.model_json_schema()

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        ch_no = int(state.get("ch_no") or self.context.current_chapter)
        chapter_outline = self.context.chapter_outline(ch_no)
        if not chapter_outline:
            raise ValueError(f"no outline entry for chapter {ch_no}; run outline first")
        extra = self.retrieved_vars(state, ch_no, outline_chapter=chapter_outline)
        extra.update(
            {
                "chapter_outline": chapter_outline,
                "volume_chapter": self.context.volume_chapter(ch_no) or {},
            }
        )
        raw = self.ask_json(purpose="chapter_plan", extra_vars=extra)
        raw["chapter_no"] = ch_no
        intent = ChapterIntent.model_validate(raw)
        plan = ChapterPlan.from_intent(intent)
        payload = plan.model_dump(mode="json")
        self.repo.save_chapter_plan(self.context.book_id, ch_no, payload)
        return {"chapter_intent": intent.model_dump(mode="json"), "chapter_plan": payload, "ch_no": ch_no}


class ChapterWriterAgent(BaseAgent):
    """Write prose from the chapter task only. Does not edit world, roster, or outline."""

    name = "chapter_writer"
    model = "writer"
    prompt_name = "chapter_writer"
    temperature = 0.8
    required_outputs = ("title", "body")

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        ch_no = int(state.get("ch_no") or self.context.current_chapter)
        plan = state.get("chapter_plan") or self.repo.load_chapter_plan(self.context.book_id, ch_no)
        if not plan:
            raise ValueError(f"no chapter plan for chapter {ch_no}; run chapter_planner first")
        raw_intent = state.get("chapter_intent") or plan.get("intent") or plan
        intent = ChapterIntent.model_validate(raw_intent)
        scenes = [ScenePlan.model_validate(item) for item in state.get("scene_plan") or []]
        if not scenes and plan.get("scenes"):
            scenes = [
                ScenePlan(
                    scene_id=f"ch{ch_no:04d}.sc{int(item.get('scene_no') or index):02d}",
                    scene_no=int(item.get("scene_no") or index),
                    location=str(item.get("location") or ""),
                    pov=str(item.get("pov_char") or ""),
                    present_characters=list(item.get("present_chars") or []),
                    scene_goal=str(item.get("goal") or ""),
                    obstacle=str(item.get("conflict") or ""),
                    covers_required_events=[intent.required_events[min(index - 1, len(intent.required_events) - 1)]] if intent.required_events else [],
                )
                for index, item in enumerate(plan.get("scenes") or [], 1)
            ]
        if not scenes:
            raise ValueError(f"no validated scene plan for chapter {ch_no}; run scene_planner first")
        title = intent.title or f"第{ch_no}章"
        extra = self.retrieved_vars(state, ch_no, chapter_plan=plan)
        extra.update(
            {
                "title": title,
                "chapter_intent": intent.model_dump(mode="json"),
                "scene_plan": [item.model_dump(mode="json") for item in scenes],
                "scenes": [item.model_dump(mode="json") for item in scenes],
                "must_not": intent.forbidden_events,
                "chapter_goal": intent.chapter_goal,
            }
        )
        body = self.ask_text(extra_vars=extra)
        draft = ChapterDraft(ch_no=ch_no, title=title, body=body)
        self.repo.save_draft(self.context.book_id, ch_no, draft.title, draft.body)
        return {
            "ch_no": ch_no,
            "title": draft.title,
            "body": draft.body,
            "word_count": draft.word_count,
            "draft": draft.model_dump(mode="json"),
        }
