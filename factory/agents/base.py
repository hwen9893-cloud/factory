"""BaseAgent: validate → prompt → model → validate. Subclasses do not call other agents or HTTP."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from factory.context import StoryContext
from factory.memory.retriever import MemoryRetriever
from factory.memory.store import MemoryStore
from factory.memory.updater import MemoryUpdater
from factory.models.client import ModelClient
from factory.prompts import PromptManager
from factory.storage import BookRepository


class AgentError(Exception):
    """Agent execution failed after retries."""


class SchemaValidationError(AgentError):
    """Required input or output fields are missing."""


@dataclass
class Runtime:
    """Services constructed once by SimpleWorkflow and injected into every agent."""

    models: ModelClient
    prompts: PromptManager
    repo: BookRepository
    context: StoryContext
    memory_store: MemoryStore
    memory_retriever: MemoryRetriever
    memory_updater: MemoryUpdater


class BaseAgent(ABC):
    """One production step. Shared: prompt render, model call, field checks, canon sync."""

    name: str = "agent.unknown"
    model: str = "planner"
    prompt_name: str = ""
    temperature: float | None = None
    max_retries: int = 2
    required_inputs: tuple[str, ...] = ()
    required_outputs: tuple[str, ...] = ()
    output_schema: dict[str, Any] = {}

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self.models = runtime.models
        self.prompts = runtime.prompts
        self.repo = runtime.repo
        self.context = runtime.context
        self.memory_store = runtime.memory_store
        self.retriever = runtime.memory_retriever
        self.updater = runtime.memory_updater

    def run(self, state: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(state or {})
        started = time.time()
        self._require(payload, self.required_inputs, "input")
        result = self._execute_with_retry(payload)
        result.setdefault("lineage", self.lineage(payload))
        result.setdefault("elapsed_sec", round(time.time() - started, 3))
        return result

    def _execute_with_retry(self, state: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        attempts = self.max_retries + 1
        for attempt in range(attempts):
            try:
                result = self.execute(state)
                self._require(result, self.required_outputs, "output")
                result.setdefault("attempts", attempt + 1)
                return result
            except SchemaValidationError as exc:
                last_error = exc
        raise AgentError(f"{self.name} failed after {attempts} attempt(s): {last_error}") from last_error

    @abstractmethod
    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def ask_json(
        self,
        *,
        purpose: str,
        extra_vars: dict[str, Any] | None = None,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rendered = self.render_prompt(**(extra_vars or {}))
        return self.models.generate_structured(
            self.messages(user=rendered["user"], system=rendered["system"]),
            schema or self.output_schema or {"type": "object"},
            profile=self.model,
            purpose=purpose,
            temperature=self.temperature,
            agent=self.name,
        )

    def ask_text(self, *, extra_vars: dict[str, Any] | None = None) -> str:
        rendered = self.render_prompt(**(extra_vars or {}))
        text = self.models.generate(
            self.messages(user=rendered["user"], system=rendered["system"]),
            profile=self.model,
            temperature=self.temperature,
            agent=self.name,
        ).strip()
        if not text:
            raise SchemaValidationError(f"{self.name} received empty model text")
        return text

    def render_prompt(self, **values: Any) -> dict[str, str]:
        return self.prompts.render(self.prompt_name, **{**self.context.prompt_vars(), **values})

    def messages(self, *, user: str, system: str = "") -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        if system:
            items.append({"role": "system", "content": system})
        items.append({"role": "user", "content": user})
        return items

    def retrieved_vars(self, state: dict[str, Any], ch_no: int, **kwargs: Any) -> dict[str, Any]:
        """Use the pipeline's retrieved packet, or fetch a bounded writer slice."""
        raw = state.get("retrieved_memory")
        if isinstance(raw, dict):
            payload = dict(raw)
            payload.setdefault("relevant_characters", raw.get("characters") or [])
            return payload
        return self.retriever.for_writer(
            ch_no,
            chapter_plan=kwargs.get("chapter_plan") or state.get("chapter_plan"),
            volume_plan=self.context.volume_plan,
            outline_chapter=kwargs.get("outline_chapter") or self.context.chapter_outline(ch_no),
            query_text=str(kwargs.get("query_text") or ""),
        ).prompt_vars()

    def chapter_text(self, state: dict[str, Any], ch_no: int) -> tuple[str, str]:
        draft = state.get("draft")
        if isinstance(draft, dict) and draft.get("body"):
            return str(draft.get("title") or f"第{ch_no}章"), str(draft["body"])
        if state.get("body"):
            return str(state.get("title") or f"第{ch_no}章"), str(state["body"])
        loaded = self.repo.load_draft(self.context.book_id, ch_no) or self.repo.load_final(self.context.book_id, ch_no)
        if not loaded:
            raise ValueError(f"no draft for chapter {ch_no}; run chapter_writer first")
        return loaded["title"], loaded["body"]

    def lineage(self, state: dict[str, Any]) -> dict[str, Any]:
        spec = self.models.settings.profile(self.model)
        result = self.models.last_result
        payload = {
            "agent": self.name,
            "profile": spec.name,
            "provider": spec.provider,
            "model": spec.model,
            "temperature": self.temperature if self.temperature is not None else spec.temperature,
            "input_ids": state.get("input_ids", []),
        }
        if result is not None:
            payload["usage"] = {
                "prompt_tokens": result.usage.prompt_tokens,
                "completion_tokens": result.usage.completion_tokens,
                "total_tokens": result.usage.total_tokens,
                "latency_ms": round(result.latency_ms, 1),
                "cost_usd": result.cost_usd,
                "attempts": result.attempts,
            }
        return payload

    def _sync_canon(self) -> None:
        memory = self.updater.sync_from_knowledge(
            world=self.context.world,
            characters=self.context.characters,
            architecture=self.context.architecture or {},
            story_seed=self.context.story_seed,
        )
        self.context.apply_memory(memory, self.memory_store.load_chapter_memories())

    def _require(self, payload: dict[str, Any], keys: tuple[str, ...], kind: str) -> None:
        missing = [key for key in keys if key not in payload or payload[key] in (None, "")]
        if missing:
            raise SchemaValidationError(f"{self.name} missing {kind} field(s): {', '.join(missing)}")
