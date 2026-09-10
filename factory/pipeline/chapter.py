"""Chapter production pipeline. The only sequencer for plan → write → review → revise → memory."""

from __future__ import annotations

import logging
from typing import Any, Callable, Iterable

from factory.agents import AGENT_CLASSES
from factory.agents.base import Runtime
from factory.context import StoryContext
from factory.storage import BookRepository
from factory.pipeline.models import (
    ChapterDraft,
    ChapterPlan,
    ChapterRecord,
    ContinuityReport,
    Decision,
    PipelineError,
    PipelineState,
    ReviewResult,
    RevisionRequest,
    StageEvent,
    retrieved_from_writer_context,
)

logger = logging.getLogger("factory.pipeline")

AGENT_TO_STAGE = {
    "chapter_planner": "chapter_planner",
    "chapter_writer": "chapter_writer",
    "continuity": "continuity_check",
    "reviewer": "quality_review",
    "revision": "revision",
    "memory": "memory_update",
}

STAGE_ORDER = (
    "load_story_context",
    "retrieve_relevant_memory",
    "chapter_planner",
    "chapter_writer",
    "continuity_check",
    "quality_review",
    "decision",
    "revision",
    "save",
    "memory_update",
    "persist",
)


class ChapterProductionPipeline:
    """Structured chapter workflow with checkpoints, resume, and a capped revision loop."""

    def __init__(
        self,
        runtime: Runtime,
        *,
        repo: BookRepository,
        context: StoryContext,
        book_id: str,
        max_revisions: int = 3,
    ) -> None:
        self.runtime = runtime
        self.repo = repo
        self.context = context
        self.max_revisions = int(max_revisions)
        self.state = PipelineState(book_id=book_id, ch_no=context.current_chapter, max_revisions=self.max_revisions)
        self.wanted: set[str] = set(STAGE_ORDER)
        self._resume_skip = False

    def run(
        self,
        *,
        ch_no: int | None = None,
        resume: bool = False,
        start_at: str | None = None,
        agents: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        self.state.ch_no = int(ch_no or self.context.current_chapter)
        self.state.max_revisions = self.max_revisions
        self.wanted = expand_stages(agents)
        if resume:
            loaded = self.repo.load_pipeline_state(self.state.book_id, self.state.ch_no)
            if loaded:
                self.state = PipelineState.model_validate(loaded)
                if self.state.status == "completed" and self.state.record:
                    self._emit("resume: chapter already completed")
                    return self._result()
                self._resume_skip = True
                self._emit(f"resume from {self.state.next_stage}")
        elif start_at:
            self.state.next_stage = start_at
            self._resume_skip = True

        self.state.status = "running"
        self._emit(f"== chapter pipeline ch={self.state.ch_no} revisions≤{self.state.max_revisions} ==")
        self._run("load_story_context", self._load_story_context)
        self._run("retrieve_relevant_memory", self._retrieve_relevant_memory)
        self._run("chapter_planner", self._chapter_planner)
        self._run("chapter_writer", self._chapter_writer)
        self._qa_loop()
        self._run("save", self._save)
        self._run("memory_update", self._memory_update)
        self._run("persist", self._persist)
        self.state.status = "completed"
        self.state.next_stage = "done"
        self._checkpoint()
        self._emit(f"== completed status={self.state.record.status if self.state.record else 'ok'} revisions={self.state.revision_attempt} ==")
        return self._result()

    def _qa_loop(self) -> None:
        qa = self.wanted & {"continuity_check", "quality_review", "decision", "revision"}
        if not qa:
            return
        if qa == {"revision"}:
            self._run("revision", self._revision)
            return
        while True:
            self._run("continuity_check", self._continuity_check)
            self._run("quality_review", self._quality_review)
            if "decision" not in self.wanted:
                break
            self._run("decision", self._decision)
            if not self.state.decision or self.state.decision.action == "save":
                break
            if self.state.revision_attempt >= self.state.max_revisions:
                self._emit(f"  max revisions ({self.state.max_revisions}), saving current draft")
                if self.state.record is None:
                    pass
                break
            if "revision" not in self.wanted:
                break
            self._run("revision", self._revision)
            self.state.revision_attempt += 1
            self._resume_skip = False
            self._emit(f"  re-review after revision {self.state.revision_attempt}/{self.state.max_revisions}")

    def _run(self, stage: str, fn: Callable[[], None]) -> None:
        if stage not in self.wanted:
            return
        prefix = stage in {"load_story_context", "retrieve_relevant_memory"}
        hold_resume = self._resume_skip and prefix
        if self._resume_skip and not prefix:
            if stage != self.state.next_stage:
                return
            self._resume_skip = False
        self._emit(f"→ {stage}")
        self.state.current_stage = stage
        self.state.log.append(StageEvent(stage=stage, status="start"))
        self._checkpoint()
        try:
            fn()
        except PipelineError:
            raise
        except Exception as exc:
            self.state.status = "failed"
            self.state.error = f"{type(exc).__name__}: {exc}"
            self.state.next_stage = stage
            self.state.log.append(StageEvent(stage=stage, status="error", detail=str(exc)))
            self._checkpoint()
            self._emit(f"  error: {exc}")
            raise PipelineError(stage, str(exc)) from exc
        self.state.log.append(StageEvent(stage=stage, status="ok"))
        if not hold_resume:
            self.state.next_stage = self._next_after(stage)
        self._emit("  ok")
        self._checkpoint()

    def _next_after(self, stage: str) -> str:
        if stage == "decision" and self.state.decision:
            return "revision" if self.state.decision.action == "revision" else "save"
        if stage == "revision":
            return "continuity_check"
        return {
            "load_story_context": "retrieve_relevant_memory",
            "retrieve_relevant_memory": "chapter_planner",
            "chapter_planner": "chapter_writer",
            "chapter_writer": "continuity_check",
            "continuity_check": "quality_review",
            "quality_review": "decision",
            "save": "memory_update",
            "memory_update": "persist",
            "persist": "done",
        }.get(stage, "done")

    def _load_story_context(self) -> None:
        ctx = self.context
        if not ctx.story_seed and not ctx.outline:
            raise ValueError("story context empty; run setup (world/outline) first")

    def _retrieve_relevant_memory(self) -> None:
        ch_no = self.state.ch_no
        plan = None
        if self.state.plan:
            plan = self.state.plan.model_dump(mode="json")
        else:
            plan = self.repo.load_chapter_plan(self.state.book_id, ch_no)
        writer_ctx = self.runtime.memory_retriever.for_writer(
            ch_no,
            chapter_plan=plan,
            volume_plan=self.context.volume_plan,
            outline_chapter=self.context.chapter_outline(ch_no),
        )
        self.state.memory = retrieved_from_writer_context(writer_ctx)

    def _run_agent(self, name: str) -> dict[str, Any]:
        return AGENT_CLASSES[name](self.runtime).run(self._agent_state())

    def _chapter_planner(self) -> None:
        result = self._run_agent("chapter_planner")
        self.state.plan = ChapterPlan.model_validate(result["chapter_plan"])

    def _chapter_writer(self) -> None:
        result = self._run_agent("chapter_writer")
        self.state.draft = ChapterDraft.model_validate(
            {
                "ch_no": result["ch_no"],
                "title": result["title"],
                "body": result["body"],
                "word_count": result.get("word_count") or len(result["body"]),
                "revision": self.state.revision_attempt,
            }
        )

    def _continuity_check(self) -> None:
        result = self._run_agent("continuity")
        extra = result.get("rule_issues") or []
        self.state.continuity = ContinuityReport.from_llm(result["continuity"], extra)

    def _quality_review(self) -> None:
        result = self._run_agent("reviewer")
        self.state.review = ReviewResult.from_llm(result["review"])

    def _decision(self) -> None:
        if not self.state.draft or not self.state.continuity or not self.state.review:
            raise ValueError("decision requires draft, continuity, and review")
        self.state.decision = decide(self.state.continuity, self.state.review, self.state.draft, self.state.revision_attempt)
        action = self.state.decision.action
        self._emit(f"  decision={action} passed={self.state.decision.passed} reasons={self.state.decision.reasons}")

    def _revision(self) -> None:
        self._require_draft()
        if self.state.review is None:
            raw = self.repo.load_review(self.state.book_id, self.state.ch_no)
            if raw:
                self.state.review = ReviewResult.from_llm(raw)
        if self.state.continuity is None:
            raw = self.repo.load_continuity(self.state.book_id, self.state.ch_no)
            if raw:
                self.state.continuity = ContinuityReport.from_llm(raw)
        result = self._run_agent("revision")
        self.state.draft = ChapterDraft.model_validate(
            {
                "ch_no": result["ch_no"],
                "title": result["title"],
                "body": result["body"],
                "word_count": result.get("word_count") or len(result["body"]),
                "revision": self.state.revision_attempt + 1,
            }
        )

    def _save(self) -> None:
        draft = self._require_draft()
        plan = self.state.plan or ChapterPlan(ch_no=draft.ch_no, title=draft.title)
        continuity = self.state.continuity or ContinuityReport()
        review = self.state.review or ReviewResult()
        if self.state.revision_attempt and (not continuity.passed or not review.passed):
            status = "max_revisions"
        elif self.state.revision_attempt:
            status = "revised"
        else:
            status = "passed"
        self.repo.save_final(self.state.book_id, draft.ch_no, draft.title, draft.body)
        self.state.record = ChapterRecord(
            ch_no=draft.ch_no,
            title=draft.title,
            body=draft.body,
            plan=plan,
            draft=draft,
            continuity=continuity,
            review=review,
            revision_attempts=self.state.revision_attempt,
            status=status,
            word_count=draft.word_count,
        )

    def _memory_update(self) -> None:
        result = self._run_agent("memory")
        self.state.memory_update = dict(result.get("memory_update") or {})

    def _persist(self) -> None:
        if self.state.record:
            self.repo.save_chapter_record(self.state.book_id, self.state.ch_no, self.state.record.model_dump(mode="json", by_alias=True))

    def _agent_state(self) -> dict[str, Any]:
        draft = self.state.draft
        plan = self.state.plan
        memory = self.state.memory
        payload: dict[str, Any] = {
            "ch_no": self.state.ch_no,
            "story_seed": self.context.story_seed,
        }
        if memory:
            payload["retrieved_memory"] = memory.model_dump(mode="json")
            payload.update(memory.model_dump(mode="json"))
        if plan:
            payload["chapter_plan"] = plan.model_dump(mode="json")
        if draft:
            payload["title"] = draft.title
            payload["body"] = draft.body
            payload["draft"] = draft.model_dump(mode="json")
        if self.state.continuity:
            payload["continuity"] = self.state.continuity.model_dump(mode="json")
        if self.state.review:
            payload["review"] = self.state.review.model_dump(mode="json", by_alias=True)
        if self.state.decision and self.state.decision.request:
            payload["revision_request"] = self.state.decision.request.model_dump(mode="json")
        if self.state.record:
            payload["chapter_record"] = self.state.record.model_dump(mode="json", by_alias=True)
        return payload

    def _require_draft(self) -> ChapterDraft:
        if self.state.draft:
            return self.state.draft
        raw = self.repo.load_final(self.state.book_id, self.state.ch_no) or self.repo.load_draft(self.state.book_id, self.state.ch_no)
        if not raw:
            raise ValueError(f"no draft for chapter {self.state.ch_no}")
        self.state.draft = ChapterDraft(ch_no=self.state.ch_no, title=raw["title"], body=raw["body"])
        return self.state.draft

    def _checkpoint(self) -> None:
        self.repo.save_pipeline_state(self.state.book_id, self.state.ch_no, self.state.model_dump(mode="json", by_alias=True))

    def _result(self) -> dict[str, Any]:
        if self.state.record:
            payload = self.state.record.as_workflow_dict()
        else:
            payload = {"ch_no": self.state.ch_no}
            if self.state.plan:
                payload["chapter_plan"] = self.state.plan.model_dump(mode="json")
            if self.state.draft:
                payload["title"] = self.state.draft.title
                payload["body"] = self.state.draft.body
                payload["word_count"] = self.state.draft.word_count
            if self.state.continuity:
                payload["continuity"] = self.state.continuity.model_dump(mode="json")
            if self.state.review:
                payload["review"] = self.state.review.model_dump(mode="json", by_alias=True)
        payload["memory_update"] = self.state.memory_update
        payload["pipeline"] = {
            "status": self.state.status,
            "revision_attempts": self.state.revision_attempt,
            "log": [item.model_dump() for item in self.state.log],
        }
        return payload

    def _emit(self, message: str) -> None:
        print(message, flush=True)
        logger.info(message)


def expand_stages(agents: Iterable[str] | None) -> set[str]:
    if not agents:
        return set(STAGE_ORDER)
    wanted = {"load_story_context", "retrieve_relevant_memory"}
    names = list(agents)
    named = set(names)
    for name in names:
        if name in AGENT_TO_STAGE:
            wanted.add(AGENT_TO_STAGE[name])
    if named == {"revision"}:
        return wanted
    if "memory" in named:
        wanted.update({"decision", "save", "persist"})
    if "revision" in named:
        wanted.update({"continuity_check", "quality_review", "decision", "revision"})
    return wanted


def decide(continuity: ContinuityReport, review: ReviewResult, draft: ChapterDraft, attempt: int) -> Decision:
    reasons: list[str] = []
    if not continuity.passed:
        reasons.append(f"continuity:{continuity.severity}")
    if not review.passed:
        reasons.append("review")
    if review.must_fix:
        reasons.append("must_fix")
    if not reasons:
        return Decision(action="save", passed=True, reasons=["ok"])
    must = list(review.must_fix)
    must.extend(item.message for item in continuity.all_conflicts if item.severity == "hard" and item.message)
    optional = list(review.optional_fix)
    optional.extend(item.message for item in continuity.all_conflicts if item.severity != "hard" and item.message)
    request = RevisionRequest(
        attempt=attempt + 1,
        draft=draft,
        continuity=continuity,
        review=review,
        must_fix=must,
        optional_fix=optional,
    )
    return Decision(action="revision", passed=False, reasons=reasons, request=request)
