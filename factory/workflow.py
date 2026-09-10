"""CLI → SimpleWorkflow.run → setup agents and/or ChapterProductionPipeline.

Call chain:

  factory.cli  (typer)
    → load_settings()                         # default.yaml < project < env < CLI
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
from factory.memory import MemoryRetriever, MemoryUpdater, build_store
from factory.models.client import ModelClient
from factory.models.usage import UsageStore
from factory.pipeline.chapter import ChapterProductionPipeline
from factory.prompts import PromptManager
from factory.settings import Settings
from factory.storage import BookRepository


class SimpleWorkflow:
    """Run a named sequence of agents against one book."""

    def __init__(self, settings: Settings, book_id: str) -> None:
        self.settings = settings
        self.book_id = book_id
        self.repo = BookRepository(settings.data_dir)
        self.prompts = PromptManager()
        self.models = ModelClient(
            settings,
            usage_store=UsageStore(settings.data_dir / "usage.sqlite"),
            book_id=book_id,
        )
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
        for name in setup:
            agent_cls = AGENT_CLASSES.get(name)
            if agent_cls is None:
                raise KeyError(f"unknown workflow step: {name}")
            print(f"→ {name}", flush=True)
            payload.update(agent_cls(self.runtime).run(payload))
            print("  ok", flush=True)
        if chapter:
            pipeline = ChapterProductionPipeline(
                self.runtime,
                repo=self.repo,
                context=self.context,
                book_id=self.book_id,
                max_revisions=self.settings.max_revisions,
            )
            payload.update(
                pipeline.run(
                    ch_no=int(payload.get("ch_no") or self.context.current_chapter),
                    resume=self.resume,
                    start_at=self.start_at,
                    agents=chapter,
                )
            )
        return payload
