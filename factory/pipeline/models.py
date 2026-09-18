"""Structured chapter-pipeline contracts. Agents pass these, not loose blobs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, computed_field, field_validator, model_validator
from factory.schema.contracts import StoryStateDelta


class SceneCard(BaseModel):
    scene_no: int = 1
    location: str = ""
    pov_char: str = ""
    present_chars: list[str] = Field(default_factory=list)
    goal: str = ""
    conflict: str = ""
    pacing: str = ""


class ChapterIntent(BaseModel):
    chapter_no: int = Field(validation_alias=AliasChoices("chapter_no", "ch_no"))
    title: str
    chapter_goal: str = Field("", validation_alias=AliasChoices("chapter_goal", "goal"))
    story_function: str = ""
    main_plot_advancement: list[str] = Field(default_factory=list)
    subplot_advancement: list[str] = Field(default_factory=list)
    character_goals: dict[str, str] = Field(default_factory=dict)
    character_changes: list[dict[str, Any]] = Field(default_factory=list)
    conflict: str = ""
    stakes: str = ""
    required_events: list[str] = Field(default_factory=list)
    foreshadowing_to_place: list[str] = Field(default_factory=list)
    foreshadowing_to_payoff: list[str] = Field(default_factory=list)
    payoff_plan: dict[str, Any] = Field(default_factory=dict)
    hook_plan: dict[str, Any] = Field(default_factory=dict)
    forbidden_events: list[str] = Field(default_factory=list, validation_alias=AliasChoices("forbidden_events", "must_not"))
    required_state_changes: list[dict[str, Any]] = Field(default_factory=list)
    word_budget: int = 0

    @model_validator(mode="after")
    def _events(self) -> "ChapterIntent":
        if not self.required_events and self.chapter_goal:
            self.required_events = [self.chapter_goal]
        return self


class ScenePlan(BaseModel):
    scene_id: str
    scene_no: int
    time: str = ""
    location: str = ""
    pov: str = Field("", validation_alias=AliasChoices("pov", "pov_char"))
    entry_state: dict[str, Any] = Field(default_factory=dict)
    present_characters: list[str] = Field(default_factory=list, validation_alias=AliasChoices("present_characters", "present_chars"))
    scene_goal: str = Field("", validation_alias=AliasChoices("scene_goal", "goal"))
    obstacle: str = Field("", validation_alias=AliasChoices("obstacle", "conflict"))
    beats: list[str] = Field(default_factory=list)
    reveal: str = ""
    payoff: str = ""
    expected_state_delta: dict[str, Any] = Field(default_factory=dict)
    transition: str = ""
    exit_hook: str = ""
    word_budget: int = 0
    covers_required_events: list[str] = Field(default_factory=list)


class ChapterPlan(BaseModel):
    ch_no: int
    title: str
    goal: str = ""
    scenes: list[SceneCard] = Field(default_factory=list)
    must_not: list[str] = Field(default_factory=list)
    intent: ChapterIntent | None = None

    @classmethod
    def from_intent(cls, intent: ChapterIntent, scenes: list[ScenePlan] | None = None) -> "ChapterPlan":
        cards = [
            SceneCard(
                scene_no=item.scene_no,
                location=item.location,
                pov_char=item.pov,
                present_chars=item.present_characters,
                goal=item.scene_goal,
                conflict=item.obstacle,
                pacing="",
            )
            for item in (scenes or [])
        ]
        return cls(ch_no=intent.chapter_no, title=intent.title, goal=intent.chapter_goal, scenes=cards, must_not=intent.forbidden_events, intent=intent)


class ChapterDraft(BaseModel):
    ch_no: int
    title: str
    body: str
    word_count: int = 0
    revision: int = 0

    @model_validator(mode="after")
    def _word_count(self) -> ChapterDraft:
        if not self.word_count:
            self.word_count = len(self.body)
        return self


class ConflictItem(BaseModel):
    severity: Literal["hard", "warn"] = "warn"
    type: str = ""
    dimension: str = ""
    message: str = ""


class ContinuityReport(BaseModel):
    character_conflicts: list[ConflictItem] = Field(default_factory=list)
    timeline_conflicts: list[ConflictItem] = Field(default_factory=list)
    world_rule_conflicts: list[ConflictItem] = Field(default_factory=list)
    item_conflicts: list[ConflictItem] = Field(default_factory=list)
    plot_conflicts: list[ConflictItem] = Field(default_factory=list)
    cultivation_conflicts: list[ConflictItem] = Field(default_factory=list)
    location_conflicts: list[ConflictItem] = Field(default_factory=list)
    knowledge_conflicts: list[ConflictItem] = Field(default_factory=list)
    golden_finger_conflicts: list[ConflictItem] = Field(default_factory=list)
    antagonist_conflicts: list[ConflictItem] = Field(default_factory=list)
    foreshadowing_conflicts: list[ConflictItem] = Field(default_factory=list)
    hook_payoff_conflicts: list[ConflictItem] = Field(default_factory=list)
    scene_coverage_conflicts: list[ConflictItem] = Field(default_factory=list)
    severity: Literal["none", "warn", "hard"] = "none"
    notes: str = ""

    @model_validator(mode="after")
    def _severity(self) -> ContinuityReport:
        items = self.all_conflicts
        if any(item.severity == "hard" for item in items):
            self.severity = "hard"
        elif items and self.severity == "none":
            self.severity = "warn"
        return self

    @computed_field
    @property
    def passed(self) -> bool:
        return self.severity != "hard"

    @property
    def all_conflicts(self) -> list[ConflictItem]:
        return (
            self.character_conflicts
            + self.timeline_conflicts
            + self.world_rule_conflicts
            + self.item_conflicts
            + self.plot_conflicts
            + self.cultivation_conflicts
            + self.location_conflicts
            + self.knowledge_conflicts
            + self.golden_finger_conflicts
            + self.antagonist_conflicts
            + self.foreshadowing_conflicts
            + self.hook_payoff_conflicts
            + self.scene_coverage_conflicts
        )

    @classmethod
    def from_llm(cls, data: dict[str, Any], extra: list[dict[str, Any]] | None = None) -> ContinuityReport:
        raw = dict(data or {})
        buckets = {
            "character_conflicts": _as_conflicts(raw.get("character_conflicts")),
            "timeline_conflicts": _as_conflicts(raw.get("timeline_conflicts")),
            "world_rule_conflicts": _as_conflicts(raw.get("world_rule_conflicts")),
            "item_conflicts": _as_conflicts(raw.get("item_conflicts")),
            "plot_conflicts": _as_conflicts(raw.get("plot_conflicts")),
            "cultivation_conflicts": _as_conflicts(raw.get("cultivation_conflicts")),
            "location_conflicts": _as_conflicts(raw.get("location_conflicts")),
            "knowledge_conflicts": _as_conflicts(raw.get("knowledge_conflicts")),
            "golden_finger_conflicts": _as_conflicts(raw.get("golden_finger_conflicts")),
            "antagonist_conflicts": _as_conflicts(raw.get("antagonist_conflicts")),
            "foreshadowing_conflicts": _as_conflicts(raw.get("foreshadowing_conflicts")),
            "hook_payoff_conflicts": _as_conflicts(raw.get("hook_payoff_conflicts")),
            "scene_coverage_conflicts": _as_conflicts(raw.get("scene_coverage_conflicts")),
        }
        for item in list(raw.get("issues") or []) + list(extra or []):
            conflict = ConflictItem.model_validate(item) if not isinstance(item, ConflictItem) else item
            buckets[_bucket_for(conflict)].append(conflict)
        report = cls(**buckets, notes=str(raw.get("notes") or ""), severity=raw.get("severity") or "none")
        if raw.get("passed") is False and report.severity != "hard":
            report.severity = "hard"
        return report


class ReviewResult(BaseModel):
    model_config = {"populate_by_name": True}

    score: float = 0
    problems: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    must_fix: list[str] = Field(default_factory=list)
    optional_fix: list[str] = Field(default_factory=list)
    passed: bool = Field(True, validation_alias=AliasChoices("pass", "passed"), serialization_alias="pass")

    @field_validator("problems", "strengths", "must_fix", "optional_fix", mode="before")
    @classmethod
    def _strings(cls, value: Any) -> list[str]:
        if not value:
            return []
        rows = []
        for item in value:
            if isinstance(item, dict):
                rows.append(str(item.get("message") or item.get("text") or item))
            else:
                rows.append(str(item))
        return rows

    @classmethod
    def from_llm(cls, data: dict[str, Any]) -> ReviewResult:
        raw = dict(data or {})
        if any(key in raw for key in ("must_fix", "problems", "optional_fix")):
            result = cls.model_validate(raw)
        else:
            issues = list(raw.get("issues") or [])
            must = [str(item.get("message") or item) for item in issues if isinstance(item, dict) and item.get("severity") == "hard"]
            optional = [str(item.get("message") or item) for item in issues if not (isinstance(item, dict) and item.get("severity") == "hard")]
            result = cls(
                score=float(raw.get("score") or 0),
                problems=[str(item.get("message") or item) for item in issues],
                strengths=[str(item) for item in (raw.get("strengths") or [])],
                must_fix=must,
                optional_fix=optional,
                passed=bool(raw.get("passed", True)),
            )
        if result.must_fix:
            result.passed = False
        return result


class RetrievedMemory(BaseModel):
    """Bounded retrieval packet. Never the full chapter archive."""

    canon: dict[str, Any] = Field(default_factory=dict)
    characters: list[dict[str, Any]] = Field(default_factory=list)
    plot_threads: list[dict[str, Any]] = Field(default_factory=list)
    volume: dict[str, Any] = Field(default_factory=dict)
    chapter_plan: dict[str, Any] = Field(default_factory=dict)
    recent_chapters: list[dict[str, Any]] = Field(default_factory=list)
    current_conflict: str = ""
    current_tasks: list[str] = Field(default_factory=list)
    recent_events: list[dict[str, Any]] = Field(default_factory=list)
    prev_tail: str = ""
    recent_summaries: str = ""


class RevisionRequest(BaseModel):
    attempt: int
    draft: ChapterDraft
    continuity: ContinuityReport
    review: ReviewResult
    must_fix: list[str] = Field(default_factory=list)
    optional_fix: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    action: Literal["save", "revision"]
    passed: bool
    reasons: list[str] = Field(default_factory=list)
    request: RevisionRequest | None = None


class ChapterRecord(BaseModel):
    ch_no: int
    title: str
    body: str
    plan: ChapterPlan
    draft: ChapterDraft
    continuity: ContinuityReport
    review: ReviewResult
    revision_attempts: int = 0
    status: Literal["passed", "revised", "max_revisions"] = "passed"
    word_count: int = 0
    operation_id: str = ""
    state_version_before: int = 0
    state_version_after: int = 0
    chapter_plan_id: str = ""
    scene_plan_ids: list[str] = Field(default_factory=list)
    continuity_issue_count: int = 0
    polish_result: str = "skipped"
    delta_id: str = ""
    finalization_status: str = "committed"

    def as_workflow_dict(self) -> dict[str, Any]:
        return {
            "ch_no": self.ch_no,
            "title": self.title,
            "body": self.body,
            "word_count": self.word_count or len(self.body),
            "chapter_plan": self.plan.model_dump(mode="json"),
            "draft": self.draft.model_dump(mode="json"),
            "continuity": self.continuity.model_dump(mode="json"),
            "review": self.review.model_dump(mode="json", by_alias=True),
            "revision_attempts": self.revision_attempts,
            "status": self.status,
            "operation_id": self.operation_id,
            "state_version_before": self.state_version_before,
            "state_version_after": self.state_version_after,
            "scene_plan_ids": self.scene_plan_ids,
            "continuity_issue_count": self.continuity_issue_count,
            "polish_result": self.polish_result,
            "finalization_status": self.finalization_status,
        }


class StageEvent(BaseModel):
    stage: str
    status: Literal["start", "ok", "error"]
    detail: str = ""


class PipelineState(BaseModel):
    book_id: str
    ch_no: int
    status: Literal["running", "failed", "completed"] = "running"
    current_stage: str = "load_story_context"
    next_stage: str = "load_story_context"
    error: str | None = None
    revision_attempt: int = 0
    max_revisions: int = 3
    memory: RetrievedMemory | None = None
    plan: ChapterPlan | None = None
    intent: ChapterIntent | None = None
    scenes: list[ScenePlan] = Field(default_factory=list)
    draft: ChapterDraft | None = None
    corrected_draft: ChapterDraft | None = None
    polished_draft: ChapterDraft | None = None
    continuity: ContinuityReport | None = None
    review: ReviewResult | None = None
    decision: Decision | None = None
    record: ChapterRecord | None = None
    memory_update: dict[str, Any] = Field(default_factory=dict)
    story_state_delta: StoryStateDelta | None = None
    log: list[StageEvent] = Field(default_factory=list)


class PipelineError(RuntimeError):
    """A pipeline stage failed. Checkpoint is already on disk."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(f"{stage}: {message}")
        self.stage = stage


def _as_conflicts(value: Any) -> list[ConflictItem]:
    rows: list[ConflictItem] = []
    for item in value or []:
        if isinstance(item, ConflictItem):
            rows.append(item)
        elif isinstance(item, dict):
            rows.append(ConflictItem.model_validate(item))
        else:
            rows.append(ConflictItem(message=str(item), severity="warn"))
    return rows


def _bucket_for(item: ConflictItem) -> str:
    key = f"{item.dimension} {item.type}".lower()
    if any(token in key for token in ("character", "char", "dead")):
        return "character_conflicts"
    if any(token in key for token in ("time", "timeline")):
        return "timeline_conflicts"
    if any(token in key for token in ("cultivation", "realm", "境界", "修炼")):
        return "cultivation_conflicts"
    if any(token in key for token in ("location", "geography", "地点", "地理")):
        return "location_conflicts"
    if any(token in key for token in ("knowledge", "认知", "知情")):
        return "knowledge_conflicts"
    if any(token in key for token in ("golden", "金手指", "cooldown")):
        return "golden_finger_conflicts"
    if any(token in key for token in ("antagonist", "反派")):
        return "antagonist_conflicts"
    if any(token in key for token in ("foreshadow", "伏笔")):
        return "foreshadowing_conflicts"
    if any(token in key for token in ("hook", "payoff", "爽点", "钩子")):
        return "hook_payoff_conflicts"
    if any(token in key for token in ("scene", "coverage", "场景", "覆盖")):
        return "scene_coverage_conflicts"
    if any(token in key for token in ("item", "artifact", "weapon")):
        return "item_conflicts"
    if any(token in key for token in ("plot", "thread", "foreshadow")):
        return "plot_conflicts"
    if any(token in key for token in ("world", "realm", "rule", "faction", "place")):
        return "world_rule_conflicts"
    return "world_rule_conflicts"


def retrieved_from_writer_context(ctx: Any) -> RetrievedMemory:
    payload = ctx.prompt_vars() if hasattr(ctx, "prompt_vars") else dict(ctx)
    return RetrievedMemory.model_validate(
        {
            "canon": payload.get("canon") or {},
            "characters": payload.get("relevant_characters") or [],
            "plot_threads": payload.get("plot_threads") or [],
            "volume": payload.get("volume") or {},
            "chapter_plan": payload.get("chapter_plan") or {},
            "recent_chapters": payload.get("recent_chapters") or [],
            "current_conflict": payload.get("current_conflict") or "",
            "current_tasks": payload.get("current_tasks") or [],
            "recent_events": payload.get("recent_events") or [],
            "prev_tail": payload.get("prev_tail") or "",
            "recent_summaries": payload.get("recent_summaries") or "",
        }
    )
