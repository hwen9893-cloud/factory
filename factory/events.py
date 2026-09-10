"""In-process workflow events. Callback only — no broker, no queue, no UI copy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

WORKFLOW_STARTED = "workflow_started"
STAGE_STARTED = "stage_started"
STAGE_COMPLETED = "stage_completed"
TOKEN = "token"
WARNING = "warning"
ERROR = "error"
WORKFLOW_COMPLETED = "workflow_completed"

# Pipeline stage id → agent id. Not display labels.
_AGENT_FOR_STAGE = {
    "chapter_planner": "chapter_planner",
    "chapter_writer": "chapter_writer",
    "continuity_check": "continuity",
    "continuity": "continuity",
    "quality_review": "reviewer",
    "reviewer": "reviewer",
    "revision": "revision",
    "memory_update": "memory",
    "memory": "memory",
    "volume_planner": "volume_planner",
    "world_builder": "world_builder",
    "character": "character",
    "novel_architect": "novel_architect",
    "outline": "outline",
}


@dataclass(frozen=True)
class WorkflowEvent:
    """What happened. Renderers decide how to show it."""

    type: str
    stage: str = ""
    agent: str = ""
    message: str = ""
    content: str = ""
    payload: dict[str, Any] | None = None
    workflow_id: str = ""
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.agent:
            object.__setattr__(self, "agent", agent_for_stage(self.stage) or self.stage)


ProgressEvent = WorkflowEvent
ProgressCallback = Callable[[WorkflowEvent], None]


def agent_for_stage(stage: str) -> str:
    return _AGENT_FOR_STAGE.get(stage, "")


def discard_progress(_event: WorkflowEvent) -> None:
    """Default sink. CLI and GUI pass their own renderer."""


def stage_started(stage: str, *, agent: str = "", message: str = "", workflow_id: str = "") -> WorkflowEvent:
    return WorkflowEvent(
        type=STAGE_STARTED,
        stage=stage,
        agent=agent,
        message=message,
        workflow_id=workflow_id,
    )


def stage_completed(stage: str, *, agent: str = "", message: str = "", workflow_id: str = "") -> WorkflowEvent:
    return WorkflowEvent(
        type=STAGE_COMPLETED,
        stage=stage,
        agent=agent,
        message=message,
        workflow_id=workflow_id,
    )


def token_event(content: str, *, agent: str = "") -> WorkflowEvent:
    return WorkflowEvent(type=TOKEN, agent=agent, stage=agent, content=content)


def error_event(message: str, *, stage: str = "", agent: str = "") -> WorkflowEvent:
    return WorkflowEvent(type=ERROR, stage=stage, agent=agent, message=message)
