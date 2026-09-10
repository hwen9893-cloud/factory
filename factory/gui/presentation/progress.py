"""Chapter workflow progress mapping. Core events stay in factory.events."""

from __future__ import annotations

from factory.events import ERROR, STAGE_COMPLETED, STAGE_STARTED, TOKEN, WORKFLOW_COMPLETED, WORKFLOW_STARTED, WorkflowEvent

# Status-bar copy for Studio. CLI has its own map.
STAGE_LABELS = {
    "chapter_planner": "Planning",
    "chapter_writer": "Writing",
    "continuity_check": "Checking continuity",
    "continuity": "Checking continuity",
    "quality_review": "Reviewing",
    "reviewer": "Reviewing",
    "revision": "Revising",
    "memory_update": "Updating memory",
    "memory": "Updating memory",
    "volume_planner": "Planning volume",
    "save": "Saving",
    "persist": "Saving",
}

# Stepper order the Studio shows. Marks (○ ● ✓) are applied here, not on the event.
TRACK_STEPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("context", "Context prepared", ("load_story_context", "retrieve_relevant_memory")),
    ("plan", "Chapter planned", ("chapter_planner",)),
    ("write", "Writing chapter", ("chapter_writer", "revision")),
    ("continuity", "Continuity check", ("continuity_check", "continuity")),
    ("review", "Review", ("quality_review", "reviewer")),
    ("memory", "Memory update", ("memory_update", "memory")),
)

_STAGE_TO_TRACK = {stage: key for key, _label, stages in TRACK_STEPS for stage in stages}

_MARK = {"pending": "○", "active": "●", "done": "✓"}
_CLASS = {"pending": "step-pending", "active": "step-active", "done": "step-done"}


def track_key(stage: str, agent: str = "") -> str:
    return _STAGE_TO_TRACK.get(stage) or _STAGE_TO_TRACK.get(agent) or ""


def track_done_stage(key: str) -> str:
    for item, _label, stages in TRACK_STEPS:
        if item == key:
            return stages[-1]
    return ""


def step_label(key: str) -> str:
    for item, label, _stages in TRACK_STEPS:
        if item == key:
            return label
    return key


def step_mark(state: str) -> str:
    return _MARK.get(state, "○")


def step_class(state: str) -> str:
    return _CLASS.get(state, "step-pending")


def status_text(event: WorkflowEvent) -> str:
    if event.type == ERROR:
        return event.message or "Error"
    if event.type == STAGE_STARTED:
        return STAGE_LABELS.get(event.stage) or STAGE_LABELS.get(event.agent) or event.stage
    return event.message or event.stage


def is_stage_start(event: WorkflowEvent) -> bool:
    return event.type == STAGE_STARTED


def is_stage_done(event: WorkflowEvent) -> bool:
    return event.type == STAGE_COMPLETED


def is_error(event: WorkflowEvent) -> bool:
    return event.type == ERROR


def is_token(event: WorkflowEvent) -> bool:
    return event.type == TOKEN


def is_workflow_start(event: WorkflowEvent) -> bool:
    return event.type == WORKFLOW_STARTED


def is_workflow_done(event: WorkflowEvent) -> bool:
    return event.type == WORKFLOW_COMPLETED
