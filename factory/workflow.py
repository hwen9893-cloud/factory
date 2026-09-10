"""Application service → SimpleWorkflow.run → setup agents and/or ChapterProductionPipeline.

Call chain:

  factory.cli / factory.gui
    → FactoryService                     # collect params live in CLI/GUI; business flow lives here
    → SimpleWorkflow(settings, book_id)
        constructs: BookRepository, PromptManager, ModelClient, StoryContext, memory, Runtime, UsageStore
    → workflow.run(step names)
        setup agents via AGENT_CLASSES
        chapter steps via ChapterProductionPipeline
    → each agent: PromptManager.render → ModelClient.generate[_structured] → Provider
    → persist through BookRepository / SchemaStore / MemoryStore

Agents never call each other or vendor SDKs. Workflow never imports OpenAI/Anthropic/Gemini.
"""

from __future__ import annotations

from typing import Any, Iterable

from factory.agents import AGENT_CLASSES, CHAPTER_AGENTS, Runtime
from factory.context import StoryContext
from factory.events import (
    WORKFLOW_COMPLETED,
    WORKFLOW_STARTED,
    ProgressCallback,
    WorkflowEvent,
    error_event,
    discard_progress,
    stage_completed,
    stage_started,
)
from factory.memory import MemoryRetriever, MemoryUpdater, build_store
from factory.models.client import ModelClient
from factory.models.registry import ModelRegistry
from factory.models.usage import UsageStore
from factory.pipeline.chapter import ChapterProductionPipeline
from factory.prompts import PromptManager
from factory.settings import Settings
from factory.storage import BookRepository


class SimpleWorkflow:
    """Run a named sequence of agents against one book."""

    def __init__(
        self,
        settings: Settings,
        book_id: str,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self.settings = settings
        self.book_id = book_id
        self.on_progress = on_progress or discard_progress
        self.repo = BookRepository(settings.data_dir)
        self.prompts = PromptManager()
        self.models = ModelClient(
            settings,
            usage_store=UsageStore.for_data_dir(settings.data_dir),
            book_id=book_id,
        )
        self.models.on_progress = self.on_progress
        self.context = StoryContext.load(
            self.repo,
            book_id,
            recent_limit=settings.recent_chapters,
            prev_tail_chars=settings.prev_tail_chars,
        )
        self.context.language = settings.language
        self.context.chapter_target_words = settings.chapter_target_words
        self.memory_store = build_store(settings.memory_backend, self.repo, book_id)
        self.memory_updater = MemoryUpdater(
            self.memory_store,
            max_major_events=settings.max_major_events,
            max_open_threads=settings.max_open_threads,
        )
        self.memory_retriever = MemoryRetriever(
            self.memory_store,
            self.repo,
            book_id,
            recent_chapters=settings.recent_chapters,
            prev_tail_chars=settings.prev_tail_chars,
            max_relevant_characters=settings.max_relevant_characters,
            max_open_threads=settings.max_open_threads,
        )
        self.context.apply_memory(self.memory_store.load(), self.memory_store.load_chapter_memories())
        self.runtime = Runtime(
            models=self.models,
            prompts=self.prompts,
            repo=self.repo,
            context=self.context,
            memory_store=self.memory_store,
            memory_retriever=self.memory_retriever,
            memory_updater=self.memory_updater,
            registry=ModelRegistry.from_settings(settings),
        )
        self.resume = False
        self.start_at: str | None = None

    def run(self, steps: Iterable[str] | None = None, state: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(state or {})
        payload.setdefault("story_seed", self.context.story_seed)
        payload.setdefault("ch_no", self.context.current_chapter)
        names = list(steps) if steps is not None else list(self.settings.workflow)
        setup = [name for name in names if name not in CHAPTER_AGENTS]
        chapter = [name for name in names if name in CHAPTER_AGENTS]
        self.on_progress(WorkflowEvent(type=WORKFLOW_STARTED, stage="workflow"))
        try:
            for name in setup:
                agent_cls = AGENT_CLASSES.get(name)
                if agent_cls is None:
                    raise KeyError(f"unknown workflow step: {name}")
                self._emit(name, "start")
                payload.update(agent_cls(self.runtime).run(payload))
                self._emit(name, "ok")
            if chapter:
                pipeline = ChapterProductionPipeline(
                    self.runtime,
                    repo=self.repo,
                    context=self.context,
                    book_id=self.book_id,
                    max_revisions=self.settings.max_revisions,
                    on_progress=self.on_progress,
                )
                payload.update(
                    pipeline.run(
                        ch_no=int(payload.get("ch_no") or self.context.current_chapter),
                        resume=self.resume,
                        start_at=self.start_at,
                        agents=chapter,
                    )
                )
        except Exception as exc:
            self.on_progress(error_event(str(exc), stage="workflow"))
            raise
        self.on_progress(WorkflowEvent(type=WORKFLOW_COMPLETED, stage="workflow"))
        return payload

    def _emit(self, stage: str, status: str, message: str = "") -> None:
        if status == "start":
            self.on_progress(stage_started(stage, message=message))
        elif status == "ok":
            self.on_progress(stage_completed(stage, message=message))
        else:
            self.on_progress(error_event(message, stage=stage))
