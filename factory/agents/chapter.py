"""Chapter production: planner makes the task, writer only writes prose."""

from __future__ import annotations

from typing import Any

from factory.agents.base import BaseAgent
from factory.pipeline.models import ChapterDraft, ChapterPlan


class ChapterPlannerAgent(BaseAgent):
    """Convert outline + volume plan + current story state into a concrete chapter task."""

    name = "chapter_planner"
    model = "planner"
    prompt_name = "chapter_planner"
    temperature = 0.35
    required_outputs = ("chapter_plan",)
    output_schema = ChapterPlan.model_json_schema()

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
        plan = self.ask_json(purpose="chapter_plan", extra_vars=extra)
        plan["ch_no"] = ch_no
        payload = ChapterPlan.model_validate(plan).model_dump(mode="json")
        self.repo.save_chapter_plan(self.context.book_id, ch_no, payload)
        return {"chapter_plan": payload, "ch_no": ch_no}


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
        title = str(plan.get("title") or f"第{ch_no}章")
        extra = self.retrieved_vars(state, ch_no, chapter_plan=plan)
        extra.update(
            {
                "title": title,
                "scenes": plan.get("scenes") or [],
                "must_not": plan.get("must_not") or [],
                "chapter_goal": plan.get("goal") or "",
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
