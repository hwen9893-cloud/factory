"""Chapter production pipeline. The only sequencer for plan → write → review → revise → memory."""

from __future__ import annotations

import logging
from typing import Any, Callable, Iterable

from factory.agents import AGENT_CLASSES
from factory.agents.base import Runtime
from factory.context import StoryContext
from factory.events import ProgressCallback, error_event, discard_progress, stage_completed, stage_started
from factory.storage import BookRepository
from factory.pipeline.models import (
    ChapterDraft,
    ChapterIntent,
    ChapterPlan,
    ChapterRecord,
    ContinuityReport,
    Decision,
    PipelineError,
    PipelineState,
    ReviewResult,
    RevisionRequest,
    ScenePlan,
    StageEvent,
    retrieved_from_writer_context,
)
from factory.pipeline.quality import FinalValidator
from factory.schema.contracts import StoryStateDelta
from factory.state import AtomicFinalizer

logger = logging.getLogger("factory.pipeline")

AGENT_TO_STAGE = {
    "chapter_planner": "chapter_planner",
    "scene_planner": "scene_planner",
    "chapter_writer": "chapter_writer",
    "continuity": "continuity_check",
    "reviewer": "quality_review",
    "revision": "revision",
    "content_revision": "content_revision",
    "style_polisher": "style_polish",
    "memory": "memory_update",
}

STAGE_ORDER = (
    "load_story_context",
    "retrieve_relevant_memory",
    "chapter_planner",
    "scene_planner",
    "chapter_writer",
    "continuity_check",
    "quality_review",
    "decision",
    "revision",
    "content_revision",
    "style_polish",
    "final_validate",
    "memory_update",
    "save",
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
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self.runtime = runtime
        self.repo = repo
        self.context = context
        self.max_revisions = int(max_revisions)
        self.on_progress = on_progress or discard_progress
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
                # Migrate checkpoints written before content/style and transactional state stages.
                if self.state.next_stage == "revision" and "content_revision" in self.wanted:
                    self.state.next_stage = "content_revision"
                if (
                    self.state.next_stage == "save"
                    and self.state.story_state_delta is None
                    and "memory_update" in self.wanted
                ):
                    self.state.next_stage = "memory_update"
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
        self._run("scene_planner", self._scene_planner)
        self._run("chapter_writer", self._chapter_writer)
        self._qa_loop()
        self.state.corrected_draft = self.state.draft
        self._run("style_polish", self._style_polish)
        self._run("final_validate", self._final_validate)
        self._run("memory_update", self._memory_update)
        self._run("save", self._save)
        self._run("persist", self._persist)
        self.state.status = "completed"
        self.state.next_stage = "done"
        self._checkpoint()
        self._emit(f"== completed status={self.state.record.status if self.state.record else 'ok'} revisions={self.state.revision_attempt} ==")
        return self._result()

    def _qa_loop(self) -> None:
        qa = self.wanted & {"continuity_check", "quality_review", "decision", "revision", "content_revision"}
        if not qa:
            return
        if qa == {"revision"}:
            self._run("revision", self._revision)
            return
        if qa == {"content_revision"}:
            self._run("content_revision", self._content_revision)
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
            revision_stage = "content_revision" if "content_revision" in self.wanted else "revision"
            if revision_stage not in self.wanted:
                break
            self._run(revision_stage, self._content_revision if revision_stage == "content_revision" else self._revision)
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
        self.state.current_stage = stage
        self._emit(f"→ {stage}", stage=stage, status="start")
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
            self._emit(str(exc), stage=stage, status="error")
            raise PipelineError(stage, str(exc)) from exc
        self.state.log.append(StageEvent(stage=stage, status="ok"))
        if not hold_resume:
            self.state.next_stage = self._next_after(stage)
        self._emit("  ok", stage=stage, status="ok")
        self._checkpoint()

    def _next_after(self, stage: str) -> str:
        if stage == "decision" and self.state.decision:
            revision_stage = "content_revision" if "content_revision" in self.wanted else "revision"
            return revision_stage if self.state.decision.action == "revision" else "style_polish"
        if stage in {"revision", "content_revision"}:
            return "continuity_check"
        return {
            "load_story_context": "retrieve_relevant_memory",
            "retrieve_relevant_memory": "chapter_planner",
            "chapter_planner": "scene_planner",
            "scene_planner": "chapter_writer",
            "chapter_writer": "continuity_check",
            "continuity_check": "quality_review",
            "quality_review": "decision",
            "style_polish": "final_validate",
            "final_validate": "memory_update",
            "memory_update": "save",
            "save": "persist",
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
        self.state.intent = ChapterIntent.model_validate(result.get("chapter_intent") or result["chapter_plan"])
        self.state.plan = ChapterPlan.model_validate(result["chapter_plan"])

    def _scene_planner(self) -> None:
        result = self._run_agent("scene_planner")
        self.state.intent = ChapterIntent.model_validate(result.get("chapter_intent") or self.state.intent)
        self.state.scenes = [ScenePlan.model_validate(item) for item in result.get("scene_plan") or []]
        self.state.plan = ChapterPlan.from_intent(self.state.intent, self.state.scenes)
        self.repo.save_chapter_plan(
            self.state.book_id,
            self.state.ch_no,
            self.state.plan.model_dump(mode="json"),
        )

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
        self._revise_with("revision")

    def _content_revision(self) -> None:
        self._revise_with("content_revision")

    def _revise_with(self, agent_name: str) -> None:
        self._require_draft()
        if self.state.review is None:
            raw = self.repo.load_review(self.state.book_id, self.state.ch_no)
            if raw:
                self.state.review = ReviewResult.from_llm(raw)
        if self.state.continuity is None:
            raw = self.repo.load_continuity(self.state.book_id, self.state.ch_no)
            if raw:
                self.state.continuity = ContinuityReport.from_llm(raw)
        result = self._run_agent(agent_name)
        self.state.draft = ChapterDraft.model_validate(
            {
                "ch_no": result["ch_no"],
                "title": result["title"],
                "body": result["body"],
                "word_count": result.get("word_count") or len(result["body"]),
                "revision": self.state.revision_attempt + 1,
            }
        )

    def _style_polish(self) -> None:
        self._require_draft()
        result = self._run_agent("style_polisher")
        self.state.polished_draft = ChapterDraft.model_validate(
            {
                "ch_no": result["ch_no"],
                "title": result["title"],
                "body": result["body"],
                "word_count": result.get("word_count") or len(result["body"]),
                "revision": self.state.revision_attempt,
            }
        )
        self.state.draft = self.state.polished_draft

    def _final_validate(self) -> None:
        corrected = self.state.corrected_draft or self._require_draft()
        polished = self.state.polished_draft or self._require_draft()
        intent = self.state.intent or (self.state.plan.intent if self.state.plan else None)
        if intent is None:
            raise ValueError("final validation requires ChapterIntent")
        result = FinalValidator().validate(
            corrected=corrected.body,
            polished=polished.body,
            intent=intent,
            scenes=self.state.scenes,
            protected_facts=self._protected_facts(),
        )
        if not result.valid:
            raise ValueError("; ".join(result.issues))

    def _protected_facts(self) -> dict[str, list[str]]:
        facts: dict[str, list[str]] = {"character": [], "cultivation": [], "location": [], "status": []}
        for char in self.context.characters:
            for category, key in (
                ("character", "name"),
                ("cultivation", "cultivation_realm"),
                ("cultivation", "sub_realm"),
                ("location", "location"),
                ("status", "status"),
            ):
                value = str(char.get(key) or "").strip()
                if value:
                    facts[category].append(value)
        return facts

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
            operation_id=self.state.story_state_delta.operation_id if self.state.story_state_delta else "",
            state_version_before=self.state.story_state_delta.base_state_version if self.state.story_state_delta else 0,
            state_version_after=(self.state.story_state_delta.base_state_version + 1) if self.state.story_state_delta else 0,
            chapter_plan_id=f"chapter-plan-{draft.ch_no:06d}",
            scene_plan_ids=[item.scene_id for item in self.state.scenes],
            continuity_issue_count=len(continuity.all_conflicts),
            polish_result="applied" if self.state.polished_draft else "skipped",
            delta_id=self.state.story_state_delta.operation_id if self.state.story_state_delta else "",
            finalization_status="committed",
        )
        if self.state.story_state_delta is None:
            raise ValueError("atomic finalization requires StoryStateDelta; run memory extraction first")

        def project_legacy_memory() -> None:
            from factory.agents.memory import persist_legacy_projection

            memory = self.runtime.memory_updater.apply(draft.ch_no, self.state.memory_update)
            persist_legacy_projection(self.repo, self.state.book_id, draft.ch_no, self.state.memory_update)
            self.context.apply_memory(memory, self.runtime.memory_store.load_chapter_memories())

        AtomicFinalizer(self.repo, self.state.book_id).finalize(
            title=draft.title,
            body=draft.body,
            record=self.state.record.model_dump(mode="json", by_alias=True),
            delta=self.state.story_state_delta,
            legacy_apply=project_legacy_memory,
        )

    def _memory_update(self) -> None:
        result = self._run_agent("memory")
        self.state.memory_update = dict(result.get("memory_update") or {})
        self.state.story_state_delta = StoryStateDelta.model_validate(result["story_state_delta"])

    def _persist(self) -> None:
        # Chapter record is committed with final text and StoryState in AtomicFinalizer.
        if not self.state.record:
            raise ValueError("no finalized chapter record")

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
        if self.state.intent:
            payload["chapter_intent"] = self.state.intent.model_dump(mode="json")
        if self.state.scenes:
            payload["scene_plan"] = [item.model_dump(mode="json") for item in self.state.scenes]
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
            if self.state.intent:
                payload["chapter_intent"] = self.state.intent.model_dump(mode="json")
            if self.state.scenes:
                payload["scene_plan"] = [item.model_dump(mode="json") for item in self.state.scenes]
            if self.state.draft:
                payload["title"] = self.state.draft.title
                payload["body"] = self.state.draft.body
                payload["word_count"] = self.state.draft.word_count
            if self.state.continuity:
                payload["continuity"] = self.state.continuity.model_dump(mode="json")
            if self.state.review:
                payload["review"] = self.state.review.model_dump(mode="json", by_alias=True)
        payload["memory_update"] = self.state.memory_update
        if self.state.story_state_delta:
            payload["story_state_delta"] = self.state.story_state_delta.model_dump(mode="json")
        payload["pipeline"] = {
            "status": self.state.status,
            "revision_attempts": self.state.revision_attempt,
            "log": [item.model_dump() for item in self.state.log],
        }
        return payload

    def _emit(self, message: str, *, stage: str = "", status: str = "info") -> None:
        current = stage or self.state.current_stage
        if status == "start":
            self.on_progress(stage_started(current))
        elif status == "ok":
            self.on_progress(stage_completed(current))
        elif status == "error":
            self.on_progress(error_event(message, stage=current))
        if status != "info" or message.startswith("==") or message.startswith("  "):
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
    # Existing user workflows may predate the explicit scene-planning stage.
    # Whenever they request both planning and writing, insert the new contract boundary.
    if "chapter_planner" in named and "chapter_writer" in named:
        wanted.add("scene_planner")
    if named == {"revision"}:
        return wanted
    if "memory" in named:
        wanted.update({"decision", "save", "persist"})
    if "revision" in named:
        wanted.update({"continuity_check", "quality_review", "decision", "revision"})
    if "content_revision" in named:
        wanted.update({"continuity_check", "quality_review", "decision", "content_revision"})
    if "style_polisher" in named:
        wanted.update({"style_polish", "final_validate"})
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
