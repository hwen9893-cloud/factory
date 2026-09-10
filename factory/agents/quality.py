"""Quality agents: Continuity checks facts, Reviewer evaluates craft, Revision edits prose."""

from __future__ import annotations

from typing import Any

from factory.agents.base import BaseAgent
from factory.pipeline.models import ChapterDraft, ContinuityReport, ReviewResult, RevisionRequest

CONTINUITY_SCHEMA = ContinuityReport.model_json_schema()
REVIEW_SCHEMA = ReviewResult.model_json_schema()


class ContinuityAgent(BaseAgent):
    """Fact checker only. Does not score writing quality."""

    name = "continuity"
    model = "reviewer"
    prompt_name = "continuity"
    temperature = 0.1
    max_retries = 1
    required_outputs = ("continuity",)
    output_schema = CONTINUITY_SCHEMA

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        ch_no = int(state.get("ch_no") or self.context.current_chapter)
        title, body = self.chapter_text(state, ch_no)
        plan = state.get("chapter_plan") or self.repo.load_chapter_plan(self.context.book_id, ch_no) or {}
        extra = self.retrieved_vars(state, ch_no, chapter_plan=plan, query_text=body[:800])
        characters = extra.get("relevant_characters") or extra.get("characters") or self.context.characters
        rule_issues = collect_continuity_issues(body, characters)
        extra.update({"body": body, "rule_issues": rule_issues, "chapter_plan": plan})
        report = ContinuityReport.from_llm(self.ask_json(purpose="continuity", extra_vars=extra), rule_issues)
        payload = report.model_dump(mode="json")
        self.repo.save_continuity(self.context.book_id, ch_no, payload)
        return {"continuity": payload, "ch_no": ch_no, "title": title, "body": body, "rule_issues": rule_issues}


class ReviewerAgent(BaseAgent):
    """Literary evaluation only. Does not rewrite and does not own canon checks."""

    name = "reviewer"
    model = "reviewer"
    prompt_name = "reviewer"
    temperature = 0.2
    max_retries = 1
    required_outputs = ("review",)
    output_schema = REVIEW_SCHEMA

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        ch_no = int(state.get("ch_no") or self.context.current_chapter)
        title, body = self.chapter_text(state, ch_no)
        plan = state.get("chapter_plan") or self.repo.load_chapter_plan(self.context.book_id, ch_no) or {}
        review = ReviewResult.from_llm(self.ask_json(purpose="review", extra_vars={"body": body, "chapter_plan": plan}))
        payload = review.model_dump(mode="json", by_alias=True)
        self.repo.save_review(self.context.book_id, ch_no, payload)
        return {"review": payload, "ch_no": ch_no, "title": title, "body": body}


class RevisionAgent(BaseAgent):
    """Rewrite from a RevisionRequest. Does not decide pass/fail and does not save final."""

    name = "revision"
    model = "writer"
    prompt_name = "revision"
    temperature = 0.55
    max_retries = 1
    required_outputs = ("title", "body")

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        ch_no = int(state.get("ch_no") or self.context.current_chapter)
        plan = state.get("chapter_plan") or self.repo.load_chapter_plan(self.context.book_id, ch_no) or {}
        request = state.get("revision_request")
        if request:
            parsed = RevisionRequest.model_validate(request)
            title, body = parsed.draft.title, parsed.draft.body
            extra = {
                "body": body,
                "must_fix": parsed.must_fix,
                "optional_fix": parsed.optional_fix,
                "continuity": parsed.continuity.model_dump(mode="json"),
                "review": parsed.review.model_dump(mode="json", by_alias=True),
                "attempt": parsed.attempt,
                "chapter_plan": plan,
            }
        else:
            title, body = self.chapter_text(state, ch_no)
            review = state.get("review") or self.repo.load_review(self.context.book_id, ch_no) or {}
            continuity = state.get("continuity") or self.repo.load_continuity(self.context.book_id, ch_no) or {}
            extra = {
                "body": body,
                "must_fix": review.get("must_fix") or [],
                "optional_fix": review.get("optional_fix") or [],
                "continuity": continuity,
                "review": review,
                "attempt": 1,
                "chapter_plan": plan,
            }
        body = self.ask_text(extra_vars=extra)
        draft = ChapterDraft(ch_no=ch_no, title=title, body=body, revision=int(extra.get("attempt") or 1))
        self.repo.save_draft(self.context.book_id, ch_no, draft.title, draft.body)
        return {
            "ch_no": ch_no,
            "title": draft.title,
            "body": draft.body,
            "changed": True,
            "word_count": draft.word_count,
            "draft": draft.model_dump(mode="json"),
        }


def collect_continuity_issues(body: str, characters: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Cheap deterministic checks; the model covers the rest. No book-specific realm names."""
    issues: list[dict[str, str]] = []
    for char in characters:
        if char.get("status") == "dead" and char.get("name") and char["name"] in body:
            issues.append(
                {
                    "severity": "hard",
                    "type": "dead_character_appears",
                    "dimension": "character",
                    "message": f"已死亡角色 {char['name']} 出现在正文中。",
                }
            )
    return issues
