"""Load YAML config plus environment and CLI overrides.

Priority (later wins): default.yaml < project config < environment < CLI.

API keys stay in `.env`. Model ids live in YAML, never in Python.
Call `load_settings()` once at process start. Agents never read env or vendor SDKs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from factory.models.types import DEFAULT_KEY_ENV, ModelProfile, resolve_profile_name

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "config" / "default.yaml"

# FACTORY_CONFIG is a file path, not a value overlay.
_ENV_OVERLAYS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("FACTORY_PROVIDER", ("provider",)),
    ("FACTORY_BOOK", ("project", "book")),
    ("FACTORY_DATA_DIR", ("storage", "data_dir")),
    ("FACTORY_BASE_URL", ("base_url",)),
    ("FACTORY_LANGUAGE", ("project", "language")),
    ("FACTORY_CHAPTER_TARGET_WORDS", ("generation", "chapter_target_words")),
    ("FACTORY_MAX_REVISION_ROUNDS", ("generation", "max_revision_rounds")),
    ("FACTORY_RECENT_CHAPTERS", ("memory", "recent_chapters")),
    ("FACTORY_STORAGE_BACKEND", ("storage", "backend")),
    ("FACTORY_MODEL_ARCHITECT", ("models", "architect", "model")),
    ("FACTORY_MODEL_PLANNER", ("models", "planner", "model")),
    ("FACTORY_MODEL_WRITER", ("models", "writer", "model")),
    ("FACTORY_MODEL_REVIEWER", ("models", "reviewer", "model")),
)


@dataclass(frozen=True)
class Settings:
    provider: str
    data_dir: Path
    default_book: str
    workflow: tuple[str, ...]
    recent_chapters: int
    prev_tail_chars: int
    base_url: str = ""
    language: str = "zh-CN"
    chapter_target_words: int = 5000
    workflows: dict[str, tuple[str, ...]] = field(default_factory=dict)
    profiles: dict[str, ModelProfile] = field(default_factory=dict)
    pricing: dict[str, dict[str, float]] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    memory_backend: str = "json"
    max_open_threads: int = 20
    max_major_events: int = 40
    max_relevant_characters: int = 8
    max_revisions: int = 2

    def profile(self, name: str) -> ModelProfile:
        keys = [name, resolve_profile_name(name)]
        if name == "architect" or resolve_profile_name(name) == "architect":
            keys.append("planner")
        for key in keys:
            if key in self.profiles:
                return self.profiles[key]
        raise KeyError(f"unknown model profile: {name}")

    def steps_for(self, name: str | None = None) -> tuple[str, ...]:
        if not name:
            return self.workflow
        if name in self.workflows:
            return self.workflows[name]
        return self.workflow


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge dicts. Nested dicts merge; lists and scalars replace."""
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def discover_project_config(explicit: Path | None = None) -> Path | None:
    """Project overlay: CLI path, else FACTORY_CONFIG, else factory.yaml, else config/local.yaml."""
    if explicit is not None:
        return explicit
    env_path = os.environ.get("FACTORY_CONFIG") or ""
    if env_path.strip():
        return Path(env_path)
    for candidate in (REPO_ROOT / "factory.yaml", REPO_ROOT / "config" / "local.yaml"):
        if candidate.is_file():
            return candidate
    return None


def load_settings(config_path: Path | None = None, overrides: dict[str, Any] | None = None) -> Settings:
    """Read defaults, merge project YAML, then env, then CLI overrides."""
    load_dotenv(REPO_ROOT / ".env")

    raw = _read_yaml(DEFAULT_CONFIG)
    project_path = discover_project_config(config_path)
    if project_path is not None:
        if not project_path.exists():
            raise FileNotFoundError(f"config not found: {project_path}")
        if project_path.resolve() != DEFAULT_CONFIG.resolve():
            raw = deep_merge(raw, _read_yaml(project_path))

    raw = deep_merge(raw, _env_overlay())
    if overrides:
        raw = deep_merge(raw, overrides)

    stamp_provider = _stamp_provider(overrides)
    return _build_settings(raw, stamp_provider=stamp_provider)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"config must be a mapping: {path}")
    return loaded


def _deep_set(raw: dict[str, Any], keys: tuple[str, ...], value: Any) -> None:
    cur = raw
    for key in keys[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[keys[-1]] = value


def _env_overlay() -> dict[str, Any]:
    overlay: dict[str, Any] = {}
    for env_name, keys in _ENV_OVERLAYS:
        value = os.environ.get(env_name)
        if value is None or value == "":
            continue
        _deep_set(overlay, keys, value)
    return overlay


def _stamp_provider(overrides: dict[str, Any] | None) -> str | None:
    """FACTORY_PROVIDER and CLI --provider replace every profile's provider."""
    env_value = os.environ.get("FACTORY_PROVIDER") or ""
    stamp = env_value or None
    if overrides and overrides.get("provider"):
        stamp = str(overrides["provider"])
    return stamp


def _as_int(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _build_settings(raw: dict[str, Any], *, stamp_provider: str | None) -> Settings:
    project = raw.get("project") or {}
    generation = raw.get("generation") or {}
    storage = raw.get("storage") or {}
    memory = raw.get("memory") or {}
    pipeline = raw.get("pipeline") or {}

    provider = stamp_provider or str(raw.get("provider") or "mock")
    default_base = str(raw.get("base_url") or os.environ.get("FACTORY_BASE_URL") or "")

    data_dir_value = str(storage.get("data_dir") or raw.get("data_dir") or "data/books")
    data_dir = Path(data_dir_value)
    if not data_dir.is_absolute():
        data_dir = REPO_ROOT / data_dir

    raw_models = raw.get("models") or raw.get("profiles") or {}
    profiles: dict[str, ModelProfile] = {}
    for name, spec in raw_models.items():
        item = dict(spec or {})
        item_provider = stamp_provider or str(item.get("provider") or provider)
        if stamp_provider:
            key_env = DEFAULT_KEY_ENV.get(item_provider, "")
        else:
            key_env = str(item.get("api_key_env") or DEFAULT_KEY_ENV.get(item_provider, ""))
        profiles[str(name)] = ModelProfile(
            name=str(name),
            provider=item_provider,
            model=str(item.get("model") or ""),
            temperature=float(item.get("temperature", 0.7)),
            timeout_sec=int(item.get("timeout_sec", 120)),
            max_tokens=int(item.get("max_tokens", 4096)),
            base_url=item.get("base_url") or default_base or None,
            api_key_env=key_env,
            max_retries=int(item.get("max_retries", 3)),
            retry_backoff_sec=float(item.get("retry_backoff_sec", 1.0)),
        )

    named = raw.get("workflows") or {}
    workflows = {str(key): tuple(value or ()) for key, value in named.items()}
    workflow = tuple(raw.get("workflow") or workflows.get("run") or ())
    pricing_raw = raw.get("pricing") or {}
    pricing = {
        str(model): {"input": float((rates or {}).get("input", 0)), "output": float((rates or {}).get("output", 0))}
        for model, rates in pricing_raw.items()
    }
    return Settings(
        provider=provider,
        data_dir=data_dir,
        default_book=str(project.get("book") or raw.get("default_book") or "demo"),
        workflow=workflow,
        recent_chapters=_as_int(memory.get("recent_chapters"), 3),
        prev_tail_chars=_as_int(memory.get("prev_tail_chars"), 400),
        base_url=default_base,
        language=str(project.get("language") or raw.get("language") or "zh-CN"),
        chapter_target_words=_as_int(generation.get("chapter_target_words"), 5000),
        workflows=workflows,
        profiles=profiles,
        pricing=pricing,
        raw=raw,
        memory_backend=str(storage.get("backend") or memory.get("backend") or "json"),
        max_open_threads=_as_int(memory.get("max_open_threads"), 20),
        max_major_events=_as_int(memory.get("max_major_events"), 40),
        max_relevant_characters=_as_int(memory.get("max_relevant_characters"), 8),
        max_revisions=_as_int(generation.get("max_revision_rounds") or pipeline.get("max_revisions"), 2),
    )
