"""Application service for CLI and GUI. Callers never talk to Agents or Providers."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from factory.agents import AGENT_CLASSES, CHAPTER_AGENTS
from factory.events import ProgressCallback, error_event, discard_progress, stage_completed, stage_started
from factory.memory import build_store
from factory.models.client import ModelClient
from factory.models.keys import env_names_for, key_configured, key_hint, scrub_secrets
from factory.models.specs import default_base_url, known_provider_ids, ping_model
from factory.models.registry import (
    AGENT_DEFAULT_MODELS,
    ROLE_AGENTS,
    ModelRegistry,
    agents_for_role,
    resolve_agent_models,
)
from factory.models.types import ModelProfile
from factory.models.usage import UsageRecord, UsageReport, UsageStore
from factory.pipeline.models import PipelineError
from factory.schema.store import SchemaStore
from factory.settings import Settings, save_model_assignments, save_runtime_settings
from factory.storage import BookRepository
from factory.workflow import SimpleWorkflow

logger = logging.getLogger("factory.service")

ARCHITECT_STEPS = ("world_builder", "character", "novel_architect", "outline")
CHAPTER_STEPS = tuple(CHAPTER_AGENTS)


# Application DTOs: business facts for CLI and GUI.
# Screen types (DashboardView, NavNode, ProviderRow, InspectorView) live in gui/presentation/.


@dataclass(frozen=True)
class ProviderStatus:
    """Whether a vendor key is present. Display names are not stored here."""

    name: str
    configured: bool
    env_names: tuple[str, ...]
    enabled: bool


@dataclass(frozen=True)
class ConnectionResult:
    provider: str
    ok: bool
    message: str
    latency_ms: float = 0.0


class _PingSettings:
    """Ephemeral ModelSettings for a one-shot connection test. Keys stay in the environment."""

    def __init__(self, profile: ModelProfile, pricing: dict[str, dict[str, float]]) -> None:
        self._profile = profile
        self.pricing = pricing

    def profile(self, name: str) -> ModelProfile:
        return self._profile


@dataclass
class ChapterResult:
    """Current chapter text and provenance. Not a Studio editor layout."""

    book_id: str
    book_title: str
    ch_no: int
    title: str
    body: str
    word_count: int
    source: str
    revision: int
    pipeline_status: str


@dataclass(frozen=True)
class BookStatus:
    book_id: str
    title: str
    genre: str
    outlined: int
    completed: int
    next_chapter: int | None
    last_final: int | None
    volume: int
    has_outline: bool
    next_resumable: bool = False
    current_chapter: int = 1


@dataclass(frozen=True)
class RuntimeSettings:
    chapter_target_words: int
    max_revision_rounds: int
    recent_chapters: int
    prev_tail_chars: int
    max_open_threads: int
    max_relevant_characters: int
    storage_backend: str
    data_dir: str
    provider_stamp: str
    language: str
    default_model: str


class FactoryService:
    """CLI/GUI façade. Commands mutate; queries return business DTOs.

    Screen aggregation (nav tree, dashboard cards, inspector tabs) lives in gui/.
    Callers collect params and display results; they do not run agents.
    """

    def __init__(self, settings: Settings, *, on_progress: ProgressCallback | None = None) -> None:
        self.settings = settings
        self.repo = BookRepository(settings.data_dir)
        self.on_progress = on_progress or discard_progress
        self.registry = ModelRegistry.from_settings(settings)

    def require_book(self, explicit: str | None = None) -> str:
        book_id = None
        for candidate in (
            explicit,
            os.environ.get("FACTORY_BOOK"),
            self.repo.current_book(),
            self.settings.default_book,
        ):
            if candidate:
                book_id = candidate
                break
        if not book_id:
            raise LookupError("no book selected. factory init <name>")
        if not self.repo.exists(book_id):
            raise LookupError(f"book not found: {book_id}. factory init {book_id}")
        self.repo.set_current_book(book_id)
        return book_id

    def init_book(
        self,
        name: str,
        *,
        title: str = "",
        genre: str = "修仙爽文",
        style: str = "克制、短句、先抑后扬",
        seed: str = "",
    ) -> Path:
        self.repo.init_book(name, title=title or name, genre=genre, style=style, story_seed=seed)
        self.repo.set_current_book(name)
        return self.repo.book_dir(name)

    def book_status(self, book_id: str) -> BookStatus:
        wf = self._workflow(book_id)
        ctx = wf.context
        outlined = ctx.outlined_chapters()
        completed = sum(1 for ch_no in outlined if self.repo.load_final(book_id, ch_no))
        nxt: int | None
        if outlined:
            nxt = next((ch_no for ch_no in outlined if not self.repo.load_final(book_id, ch_no)), None)
        else:
            nxt = (self.repo.max_final_chapter(book_id) or 0) + 1
        resume = False
        if nxt:
            pipe = self.repo.load_pipeline_state(book_id, nxt) or {}
            resume = pipe.get("status") in {"failed", "running"}
        return BookStatus(
            book_id=book_id,
            title=str(ctx.title or book_id),
            genre=str(ctx.genre or ""),
            outlined=len(outlined),
            completed=completed,
            next_chapter=nxt,
            last_final=self.repo.max_final_chapter(book_id),
            volume=int(ctx.current_volume or 1),
            has_outline=bool(ctx.outline),
            next_resumable=resume,
            current_chapter=int(ctx.current_chapter or 1),
        )

    def architect(self, book_id: str) -> dict[str, Any]:
        return self._invoke(book_id, ARCHITECT_STEPS)

    def plan_volume(self, book_id: str, volume_no: int) -> dict[str, Any]:
        return self._invoke(book_id, ("volume_planner",), volume_no=volume_no)

    def produce_chapter(
        self,
        book_id: str,
        ch_no: int,
        *,
        resume: bool | None = None,
        model: str | None = None,
        target_words: int | None = None,
    ) -> dict[str, Any]:
        """Full chapter pipeline: plan → write → continuity → review → revise → save → memory."""
        if resume is None:
            pipe = self.repo.load_pipeline_state(book_id, ch_no) or {}
            resume = pipe.get("status") in {"failed", "running"}
        return self._run(
            book_id,
            ch_no,
            CHAPTER_STEPS,
            resume=bool(resume),
            model=model,
            target_words=target_words,
        )

    def continue_next(self, book_id: str) -> dict[str, Any]:
        status = self.book_status(book_id)
        if not status.has_outline:
            raise ValueError("no outline. run: factory architect")
        if status.next_chapter is None:
            return {
                "done": True,
                "book_id": book_id,
                "outlined": status.outlined,
                "completed": status.completed,
            }
        result = self.produce_chapter(book_id, status.next_chapter, resume=status.next_resumable)
        result["done"] = False
        result["resumed"] = status.next_resumable
        return result

    def memory_overview(self, book_id: str, *, last_n: int | None = None) -> dict[str, Any]:
        n = self.settings.recent_chapters if last_n is None else int(last_n)
        store = build_store(self.settings.memory_backend, self.repo, book_id)
        memory = store.load()
        chapters = store.load_chapter_memories(last_n=n)
        return {
            "conflict": memory.plot.current_conflict or "",
            "facts": list(memory.canon.facts),
            "threads": [
                {"id": thread.id, "text": thread.text, "status": thread.status}
                for thread in memory.plot.open_threads
            ],
            "recent": [{"ch_no": item.ch_no, "summary": item.summary or ""} for item in chapters],
            "canon": memory.canon.to_dict(),
            "characters": memory.entities.character_list(),
            "recent_n": n,
        }

    def list_characters(self, book_id: str) -> list[dict[str, Any]]:
        return list(self.repo.load_characters(book_id) or [])

    def list_plot(self, book_id: str) -> dict[str, list[dict[str, Any]]]:
        schema = SchemaStore(self.repo, book_id).load()
        return {
            "threads": [item.model_dump() for item in schema.plot_threads],
            "foreshadowing": [item.model_dump() for item in schema.foreshadowing],
        }

    def story_bible(self, book_id: str) -> dict[str, Any]:
        schema = SchemaStore(self.repo, book_id).load()
        return schema.model_dump(mode="json")

    def save_world_bible(
        self,
        book_id: str,
        *,
        summary: str | None = None,
        rules: list[str] | None = None,
    ) -> dict[str, Any]:
        store = SchemaStore(self.repo, book_id)
        world = store.load().world
        patch: dict[str, Any] = {}
        if summary is not None:
            patch["summary"] = summary
        if rules is not None:
            patch["rules"] = [line.strip() for line in rules if str(line).strip()]
        if patch:
            world = world.merge(patch)
            store.save_world(world)
        return store.load().world.model_dump(mode="json")

    def save_character_bible(self, book_id: str, character_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        cleaned = {
            key: value
            for key, value in dict(patch or {}).items()
            if key in {
                "name",
                "personality",
                "cultivation_realm",
                "sub_realm",
                "faction",
                "location",
                "status",
                "secrets",
                "goals",
                "voice_style",
            }
        }
        character = SchemaStore(self.repo, book_id).update_character(character_id, cleaned)
        return character.model_dump(mode="json")

    def outline_detail(
        self,
        book_id: str,
        *,
        volume_no: int | None = None,
        ch_no: int | None = None,
    ) -> dict[str, Any]:
        outline = self.repo.load_outline(book_id) or {}
        architecture = self.repo.load_architecture(book_id) or {}
        if ch_no:
            chapter = _outline_chapter(outline, ch_no) or {}
            volume = next(
                (
                    item
                    for item in outline.get("volumes") or []
                    for row in item.get("chapters") or []
                    if int(row.get("ch_no") or 0) == int(ch_no)
                ),
                None,
            )
            return {
                "kind": "chapter",
                "ch_no": int(ch_no),
                "volume_no": int((volume or {}).get("volume_no") or 0) or None,
                "chapter": chapter,
                "plan": self.repo.load_chapter_plan(book_id, ch_no),
                "review": self.repo.load_review(book_id, ch_no),
                "continuity": self.repo.load_continuity(book_id, ch_no),
                "status": self.chapter_status(book_id, ch_no),
            }
        if volume_no:
            volume = next(
                (item for item in outline.get("volumes") or [] if int(item.get("volume_no") or 0) == int(volume_no)),
                {},
            )
            return {
                "kind": "volume",
                "volume_no": int(volume_no),
                "volume": volume,
                "plan": self.repo.load_volume_plan(book_id, volume_no),
            }
        return {
            "kind": "book",
            "architecture": architecture,
            "outline": outline,
        }

    def runtime_settings(self) -> RuntimeSettings:
        return RuntimeSettings(
            chapter_target_words=self.settings.chapter_target_words,
            max_revision_rounds=self.settings.max_revisions,
            recent_chapters=self.settings.recent_chapters,
            prev_tail_chars=self.settings.prev_tail_chars,
            max_open_threads=self.settings.max_open_threads,
            max_relevant_characters=self.settings.max_relevant_characters,
            storage_backend=self.settings.memory_backend,
            data_dir=str(self.settings.data_dir),
            provider_stamp=self.settings.provider,
            language=self.settings.language,
            default_model=self.settings.default_model,
        )

    def save_runtime(
        self,
        *,
        chapter_target_words: int | None = None,
        max_revision_rounds: int | None = None,
        recent_chapters: int | None = None,
        prev_tail_chars: int | None = None,
        max_open_threads: int | None = None,
        max_relevant_characters: int | None = None,
        storage_backend: str | None = None,
        persist: bool = False,
        path: Path | None = None,
    ) -> RuntimeSettings:
        generation: dict[str, Any] = {}
        memory: dict[str, Any] = {}
        storage: dict[str, Any] = {}
        changes: dict[str, Any] = {}
        if chapter_target_words is not None:
            generation["chapter_target_words"] = int(chapter_target_words)
            changes["chapter_target_words"] = int(chapter_target_words)
        if max_revision_rounds is not None:
            generation["max_revision_rounds"] = int(max_revision_rounds)
            changes["max_revisions"] = int(max_revision_rounds)
        if recent_chapters is not None:
            memory["recent_chapters"] = int(recent_chapters)
            changes["recent_chapters"] = int(recent_chapters)
        if prev_tail_chars is not None:
            memory["prev_tail_chars"] = int(prev_tail_chars)
            changes["prev_tail_chars"] = int(prev_tail_chars)
        if max_open_threads is not None:
            memory["max_open_threads"] = int(max_open_threads)
            changes["max_open_threads"] = int(max_open_threads)
        if max_relevant_characters is not None:
            memory["max_relevant_characters"] = int(max_relevant_characters)
            changes["max_relevant_characters"] = int(max_relevant_characters)
        if storage_backend is not None:
            backend = str(storage_backend).strip().lower() or "json"
            if backend not in {"json", "sqlite"}:
                raise ValueError("unknown storage backend")
            storage["backend"] = backend
            changes["memory_backend"] = backend
        if changes:
            self.settings = replace(self.settings, **changes)
        if persist:
            save_runtime_settings(
                generation=generation or None,
                memory=memory or None,
                storage=storage or None,
                path=path,
            )
        return self.runtime_settings()

    def usage_summary(self, *, book_id: str | None = None) -> UsageReport:
        store = UsageStore.for_data_dir(self.settings.data_dir)
        return store.summarize(since=store.today_start(), book_id=book_id)

    def recent_usage(self, *, book_id: str | None = None, limit: int = 5) -> tuple[UsageRecord, ...]:
        return UsageStore.for_data_dir(self.settings.data_dir).recent(book_id=book_id, limit=limit)

    def resolve_book(self, explicit: str | None = None) -> str | None:
        for candidate in (
            explicit,
            os.environ.get("FACTORY_BOOK"),
            self.repo.current_book(),
            self.settings.default_book,
        ):
            if candidate and self.repo.exists(candidate):
                return candidate
        books = self.repo.list_books()
        return books[0] if books else None

    def provider_statuses(self) -> tuple[ProviderStatus, ...]:
        """Presence of env vars only. Never includes secret values."""
        ordered: list[str] = []
        seen: set[str] = set()
        for name in (*known_provider_ids(), *self.registry.providers):
            key = str(name or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            ordered.append(key)
        return tuple(self._provider_status(name) for name in ordered)

    def test_connection(self, provider: str) -> ConnectionResult:
        """Ping a vendor through ModelClient. GUI must not call SDKs directly."""
        name = (provider or "").strip().lower()
        known = set(known_provider_ids()) | set(self.registry.providers)
        if not name or name not in known:
            return ConnectionResult(provider=name, ok=False, message="unknown provider")
        info = self.registry.providers.get(name)
        env_name = info.api_key_env if info else ""
        if not key_configured(name, env_name):
            hint = key_hint(name, env_name)
            message = f"missing API key. Set {hint}." if hint else "missing API key."
            return ConnectionResult(provider=name, ok=False, message=message)
        spec = self._ping_profile(name)
        client = ModelClient(_PingSettings(spec, self.settings.pricing), usage_store=None)
        started = time.perf_counter()
        try:
            client.generate(
                [{"role": "user", "content": "Reply with the single word pong."}],
                profile=spec.name,
                max_tokens=8,
                agent="connection_test",
            )
        except Exception as exc:
            message = scrub_secrets(str(exc)) or "failed"
            logger.warning("connection test provider=%s failed: %s", name, message)
            return ConnectionResult(provider=name, ok=False, message=message)
        latency = (time.perf_counter() - started) * 1000
        logger.info("connection test provider=%s ok latency_ms=%.0f", name, latency)
        return ConnectionResult(provider=name, ok=True, message="ok", latency_ms=latency)

    def _provider_status(self, name: str) -> ProviderStatus:
        info = self.registry.providers.get(name)
        env_name = info.api_key_env if info else ""
        enabled = info.enabled if info is not None else True
        return ProviderStatus(
            name=name,
            configured=key_configured(name, env_name),
            env_names=env_names_for(name, env_name),
            enabled=enabled,
        )

    def _ping_profile(self, provider: str) -> ModelProfile:
        info = self.registry.providers.get(provider)
        env_name = (info.api_key_env if info else "") or ""
        base = (info.base_url if info else "") or default_base_url(provider)
        for spec in self.registry.profiles.values():
            if spec.provider.strip().lower() == provider:
                timeout = min(int(spec.timeout_sec or 20), 20)
                return replace(
                    spec,
                    name=f"__ping_{provider}",
                    temperature=0.0,
                    timeout_sec=timeout,
                    max_tokens=8,
                    max_retries=0,
                    api_key_env=spec.api_key_env or env_name,
                    base_url=spec.base_url or (base or None),
                )
        return ModelProfile(
            name=f"__ping_{provider}",
            provider=provider,
            model=ping_model(provider),
            temperature=0.0,
            timeout_sec=20,
            max_tokens=8,
            base_url=base or None,
            api_key_env=env_name,
            max_retries=0,
        )

    def set_default_model(self, profile_id: str, *, persist: bool = False) -> None:
        profile_id = profile_id.strip()
        if profile_id:
            self._require_profile(profile_id)
        overrides = {agent: name for agent, name in self.settings.agent_overrides.items() if name != profile_id}
        self._commit_assignments(profile_id, overrides, persist=persist)

    def set_role_model(self, role: str, profile_id: str | None, *, persist: bool = False) -> None:
        if role not in ROLE_AGENTS:
            raise KeyError(f"unknown role: {role}")
        chosen = (profile_id or "").strip()
        default_id = self.settings.default_model
        overrides = dict(self.settings.agent_overrides)
        inherit = not chosen or chosen == default_id
        if inherit:
            for agent in agents_for_role(role):
                overrides.pop(agent, None)
        else:
            self._require_profile(chosen)
            for agent in agents_for_role(role):
                overrides[agent] = chosen
        self._commit_assignments(default_id, overrides, persist=persist)

    def set_agent_model(self, agent: str, profile_id: str | None, *, persist: bool = False) -> None:
        if agent not in AGENT_DEFAULT_MODELS:
            raise KeyError(f"unknown agent: {agent}")
        chosen = (profile_id or "").strip()
        overrides = dict(self.settings.agent_overrides)
        if not chosen or chosen == self.settings.default_model:
            overrides.pop(agent, None)
        else:
            self._require_profile(chosen)
            overrides[agent] = chosen
        self._commit_assignments(self.settings.default_model, overrides, persist=persist)

    def _require_profile(self, profile_id: str) -> None:
        self.registry.get_model(profile_id)

    def _commit_assignments(self, default_model: str, overrides: dict[str, str], *, persist: bool) -> None:
        resolved = resolve_agent_models(overrides, default_model)
        self.settings = replace(
            self.settings,
            default_model=default_model,
            agent_overrides=dict(overrides),
            agent_models=resolved,
        )
        self.registry = ModelRegistry.from_settings(self.settings)
        if persist:
            save_model_assignments(default_model=default_model, overrides=overrides)

    def chapter_status(self, book_id: str, ch_no: int) -> str:
        pipe = self.repo.load_pipeline_state(book_id, ch_no) or {}
        status = str(pipe.get("status") or "")
        if status in {"failed", "running"}:
            return status
        if self.repo.load_final(book_id, ch_no):
            return "final"
        if self.repo.load_draft(book_id, ch_no):
            return "draft"
        if self.repo.load_chapter_plan(book_id, ch_no):
            return "planned"
        return "outlined"

    def chapter_statuses(self, book_id: str) -> dict[int, str]:
        outline = self.repo.load_outline(book_id) or {}
        statuses: dict[int, str] = {}
        for volume in outline.get("volumes") or []:
            for chapter in volume.get("chapters") or []:
                ch_no = int(chapter.get("ch_no") or 0)
                if ch_no:
                    statuses[ch_no] = self.chapter_status(book_id, ch_no)
        return statuses

    def load_chapter(self, book_id: str, ch_no: int) -> ChapterResult:
        meta = self.repo.load_meta(book_id)
        loaded = self.repo.load_draft(book_id, ch_no) or self.repo.load_final(book_id, ch_no)
        source = "empty"
        title = ""
        body = ""
        if self.repo.load_draft(book_id, ch_no):
            loaded = self.repo.load_draft(book_id, ch_no)
            source = "draft"
        elif self.repo.load_final(book_id, ch_no):
            loaded = self.repo.load_final(book_id, ch_no)
            source = "final"
        if loaded:
            title = loaded.get("title") or ""
            body = loaded.get("body") or ""
        if not title:
            outline = _outline_chapter(self.repo.load_outline(book_id), ch_no)
            title = str((outline or {}).get("title") or f"第{ch_no}章")
        pipe = self.repo.load_pipeline_state(book_id, ch_no) or {}
        revision = int(pipe.get("revision_attempt") or 0)
        pipeline_status = str(pipe.get("status") or source)
        return ChapterResult(
            book_id=book_id,
            book_title=str(meta.get("title") or book_id),
            ch_no=ch_no,
            title=title,
            body=body,
            word_count=len(body),
            source=source,
            revision=revision,
            pipeline_status=pipeline_status,
        )

    def save_chapter(self, book_id: str, ch_no: int, title: str, body: str) -> ChapterResult:
        self.repo.save_draft(book_id, ch_no, title.strip() or f"第{ch_no}章", body)
        return self.load_chapter(book_id, ch_no)

    def add_chapter(self, book_id: str, *, volume_no: int | None = None) -> int:
        outline = self.repo.load_outline(book_id)
        if not outline or not outline.get("volumes"):
            raise ValueError("no outline. run: factory architect")
        volumes = list(outline.get("volumes") or [])
        target = None
        if volume_no is not None:
            target = next((item for item in volumes if int(item.get("volume_no") or 0) == int(volume_no)), None)
        if target is None:
            target = volumes[-1]
        existing = [
            int(chapter.get("ch_no") or 0)
            for volume in volumes
            for chapter in volume.get("chapters") or []
        ]
        ch_no = max(existing, default=0) + 1
        chapters = target.setdefault("chapters", [])
        chapters.append(
            {
                "ch_no": ch_no,
                "title": f"第{ch_no}章",
                "key_events": [],
                "char_focus": [],
                "hook": "",
            }
        )
        self.repo.save_outline(book_id, outline)
        meta = self.repo.load_meta(book_id)
        meta["target_chapters"] = max(int(meta.get("target_chapters") or 0), ch_no)
        self.repo.save_meta(book_id, meta)
        self.repo.save_draft(book_id, ch_no, f"第{ch_no}章", "")
        return ch_no

    def writer_context(self, book_id: str, ch_no: int) -> dict[str, Any]:
        wf = self._workflow(book_id)
        plan = wf.repo.load_chapter_plan(book_id, ch_no)
        ctx = wf.memory_retriever.for_writer(
            ch_no,
            chapter_plan=plan,
            volume_plan=wf.context.volume_plan,
            outline_chapter=wf.context.chapter_outline(ch_no),
        )
        vars_ = ctx.prompt_vars()
        return {
            "characters": vars_.get("character_context") or vars_.get("relevant_characters") or [],
            "plot": vars_.get("plot_context") or vars_.get("plot_threads") or [],
            "world": vars_.get("world_context") or vars_.get("canon") or {},
            "recent_context": vars_.get("recent_context") or "",
        }

    def memory_view(self, book_id: str, ch_no: int) -> dict[str, Any]:
        pipe = self.repo.load_pipeline_state(book_id, ch_no) or {}
        applied = dict(pipe.get("memory_update") or {})
        if not applied:
            store = build_store(self.settings.memory_backend, self.repo, book_id)
            for item in store.load_chapter_memories():
                if int(item.ch_no) == int(ch_no):
                    applied = item.to_dict()
                    break
        if applied:
            return {
                "applied": True,
                "summary": applied.get("summary") or "",
                "character_changes": applied.get("character_changes") or [],
                "new_facts": applied.get("new_facts") or applied.get("facts") or [],
                "unresolved_threads": applied.get("unresolved_threads") or [],
                "resolved_threads": applied.get("resolved_threads") or [],
                "current_conflict": applied.get("current_conflict") or "",
                "current_tasks": applied.get("current_tasks") or [],
            }
        return {
            "applied": False,
            "summary": "",
            "character_changes": [],
            "new_facts": [],
            "unresolved_threads": [],
            "resolved_threads": [],
            "current_conflict": "",
            "current_tasks": [],
        }

    def plan(
        self,
        book_id: str,
        ch_no: int,
        *,
        title: str = "",
        body: str = "",
        model: str | None = None,
        target_words: int | None = None,
    ) -> dict[str, Any]:
        self._stash(book_id, ch_no, title, body)
        return self._run(book_id, ch_no, ("chapter_planner",), model=model, target_words=target_words)

    def generate(
        self,
        book_id: str,
        ch_no: int,
        *,
        title: str = "",
        body: str = "",
        model: str | None = None,
        target_words: int | None = None,
    ) -> dict[str, Any]:
        self._stash(book_id, ch_no, title, body)
        steps: tuple[str, ...] = ("chapter_writer",)
        if not self.repo.load_chapter_plan(book_id, ch_no):
            steps = ("chapter_planner", "chapter_writer")
        return self._run(book_id, ch_no, steps, model=model, target_words=target_words)

    def review(
        self,
        book_id: str,
        ch_no: int,
        *,
        title: str = "",
        body: str = "",
        model: str | None = None,
        target_words: int | None = None,
    ) -> dict[str, Any]:
        self._stash(book_id, ch_no, title, body)
        return self._run(book_id, ch_no, ("continuity", "reviewer"), model=model, target_words=target_words)

    def revise(
        self,
        book_id: str,
        ch_no: int,
        *,
        title: str = "",
        body: str = "",
        model: str | None = None,
        target_words: int | None = None,
    ) -> dict[str, Any]:
        self._stash(book_id, ch_no, title, body)
        return self._run(book_id, ch_no, ("revision",), model=model, target_words=target_words)

    def continue_generate(
        self,
        book_id: str,
        ch_no: int,
        *,
        title: str = "",
        body: str = "",
        model: str | None = None,
        target_words: int | None = None,
    ) -> dict[str, Any]:
        self._stash(book_id, ch_no, title, body)
        pipe = self.repo.load_pipeline_state(book_id, ch_no) or {}
        if pipe.get("status") in {"failed", "running"}:
            return self._run(
                book_id,
                ch_no,
                CHAPTER_STEPS,
                resume=True,
                model=model,
                target_words=target_words,
            )
        return self.generate(book_id, ch_no, model=model, target_words=target_words)

    def accept(
        self,
        book_id: str,
        ch_no: int,
        *,
        title: str,
        body: str,
        model: str | None = None,
        target_words: int | None = None,
    ) -> dict[str, Any]:
        heading = title.strip() or f"第{ch_no}章"
        self.repo.save_draft(book_id, ch_no, heading, body)
        self.repo.save_final(book_id, ch_no, heading, body)
        meta = self.repo.load_meta(book_id)
        meta["current_chapter"] = ch_no
        self.repo.save_meta(book_id, meta)
        if not body.strip():
            return {"ch_no": ch_no, "title": heading, "body": body, "accepted": True}
        wf = self._workflow(book_id, model=model, target_words=target_words)
        wf.context.current_chapter = ch_no
        wf.context.save_meta(wf.repo)
        self._progress("memory", "start")
        result = AGENT_CLASSES["memory"](wf.runtime).run(
            {
                "story_seed": wf.context.story_seed,
                "ch_no": ch_no,
                "title": heading,
                "body": body,
            }
        )
        self._progress("memory", "ok")
        result["accepted"] = True
        return result

    def _stash(self, book_id: str, ch_no: int, title: str, body: str) -> None:
        if title.strip() or body.strip():
            self.save_chapter(book_id, ch_no, title, body)

    def _run(
        self,
        book_id: str,
        ch_no: int,
        steps: tuple[str, ...],
        *,
        resume: bool = False,
        model: str | None = None,
        target_words: int | None = None,
    ) -> dict[str, Any]:
        return self._invoke(
            book_id,
            steps,
            ch_no=ch_no,
            resume=resume,
            model=model,
            target_words=target_words,
            require_outline=True,
        )

    def _invoke(
        self,
        book_id: str,
        steps: tuple[str, ...],
        *,
        ch_no: int | None = None,
        volume_no: int | None = None,
        resume: bool = False,
        model: str | None = None,
        target_words: int | None = None,
        require_outline: bool = False,
    ) -> dict[str, Any]:
        wf = self._workflow(book_id, model=model, target_words=target_words)
        if require_outline and not wf.context.outline:
            raise ValueError("no outline. run: factory architect")
        chapter_steps = any(name in CHAPTER_AGENTS for name in steps)
        if ch_no:
            wf.context.current_chapter = ch_no
        if chapter_steps:
            if not ch_no:
                ch_no = int(wf.context.current_chapter or 1)
            if not wf.context.outline:
                raise ValueError("no outline. run: factory architect")
            self._ensure_volume(wf, ch_no)
            volume_no = volume_no or wf.context.volume_for_chapter(ch_no)
        if volume_no:
            wf.context.current_volume = volume_no
            loaded = wf.repo.load_volume_plan(book_id, volume_no)
            if loaded:
                wf.context.volume_plan = loaded
        wf.resume = resume
        wf.context.save_meta(wf.repo)
        payload = {
            "story_seed": wf.context.story_seed,
            "ch_no": ch_no or wf.context.current_chapter,
            "volume_no": volume_no or wf.context.current_volume,
        }
        try:
            return wf.run(steps, payload)
        except PipelineError:
            raise

    def _ensure_volume(self, wf: SimpleWorkflow, ch_no: int) -> None:
        volume_no = wf.context.volume_for_chapter(ch_no)
        if wf.repo.load_volume_plan(wf.book_id, volume_no):
            return
        wf.context.current_volume = volume_no
        wf.context.current_chapter = ch_no
        wf.context.save_meta(wf.repo)
        wf.run(("volume_planner",), {"volume_no": volume_no, "ch_no": ch_no})

    def _workflow(
        self,
        book_id: str,
        *,
        model: str | None = None,
        target_words: int | None = None,
    ) -> SimpleWorkflow:
        settings = self.settings
        changes: dict[str, Any] = {}
        if target_words:
            changes["chapter_target_words"] = int(target_words)
        if model:
            changes["agent_models"] = {
                **settings.agent_models,
                "chapter_writer": model,
                "revision": model,
            }
        if changes:
            settings = replace(settings, **changes)
        return SimpleWorkflow(settings, book_id, on_progress=self.on_progress)

    def _progress(self, stage: str, status: str, message: str = "") -> None:
        if status == "start":
            self.on_progress(stage_started(stage, message=message))
        elif status == "ok":
            self.on_progress(stage_completed(stage, message=message))
        else:
            self.on_progress(error_event(message, stage=stage))


def _outline_chapter(outline: dict[str, Any] | None, ch_no: int) -> dict[str, Any] | None:
    for volume in (outline or {}).get("volumes") or []:
        for chapter in volume.get("chapters") or []:
            if int(chapter.get("ch_no") or 0) == ch_no:
                return chapter
    return None
