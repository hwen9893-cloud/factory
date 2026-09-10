"""Agent registry. Workflow looks up by name; agents never call each other."""

from factory.agents.architect import NovelArchitectAgent, OutlineAgent, VolumePlannerAgent
from factory.agents.base import AgentError, BaseAgent, Runtime, SchemaValidationError
from factory.agents.chapter import ChapterPlannerAgent, ChapterWriterAgent
from factory.agents.memory import MemoryAgent
from factory.agents.quality import ContinuityAgent, ReviewerAgent, RevisionAgent
from factory.agents.setting import CharacterAgent, WorldBuilderAgent

AGENT_CLASSES: dict[str, type[BaseAgent]] = {
    "world_builder": WorldBuilderAgent,
    "character": CharacterAgent,
    "novel_architect": NovelArchitectAgent,
    "outline": OutlineAgent,
    "volume_planner": VolumePlannerAgent,
    "chapter_planner": ChapterPlannerAgent,
    "chapter_writer": ChapterWriterAgent,
    "continuity": ContinuityAgent,
    "reviewer": ReviewerAgent,
    "revision": RevisionAgent,
    "memory": MemoryAgent,
}

CHAPTER_AGENTS = frozenset(
    {
        "chapter_planner",
        "chapter_writer",
        "continuity",
        "reviewer",
        "revision",
        "memory",
    }
)

__all__ = [
    "AGENT_CLASSES",
    "CHAPTER_AGENTS",
    "AgentError",
    "BaseAgent",
    "Runtime",
    "SchemaValidationError",
    "WorldBuilderAgent",
    "CharacterAgent",
    "NovelArchitectAgent",
    "OutlineAgent",
    "VolumePlannerAgent",
    "ChapterPlannerAgent",
    "ChapterWriterAgent",
    "ContinuityAgent",
    "ReviewerAgent",
    "RevisionAgent",
    "MemoryAgent",
]
