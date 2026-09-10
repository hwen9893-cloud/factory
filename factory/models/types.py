"""Shared types for the model layer. Agents import these, never vendor SDKs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "GenerationConfig",
    "GenerationResult",
    "ModelProfile",
    "PROFILE_ALIASES",
    "Usage",
    "estimate_cost",
    "resolve_profile_name",
    "usage_from_counts",
]


@dataclass(frozen=True)
class GenerationConfig:
    """Per-call sampling and limits. Profile supplies defaults; callers may override."""

    temperature: float = 0.7
    max_tokens: int = 4096
    timeout_sec: float = 120.0
    top_p: float | None = None


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class GenerationResult:
    """Text plus metadata. Agents usually only read `.text`; lineage reads the rest."""

    text: str
    model: str
    provider: str
    usage: Usage = field(default_factory=Usage)
    latency_ms: float = 0.0
    cost_usd: float | None = None
    attempts: int = 1


@dataclass(frozen=True)
class ModelProfile:
    """Named catalog entry (role slot or preset such as qwen_writer)."""

    name: str
    provider: str
    model: str
    temperature: float = 0.7
    timeout_sec: int = 120
    max_tokens: int = 4096
    base_url: str | None = None
    api_key_env: str = ""
    max_retries: int = 3
    retry_backoff_sec: float = 1.0
    display_name: str = ""
    roles: tuple[str, ...] = ()


PROFILE_ALIASES = {
    "plan": "planner",
    "write": "writer",
    "review": "reviewer",
}


def resolve_profile_name(name: str) -> str:
    return PROFILE_ALIASES.get(name, name)


def usage_from_counts(prompt: int = 0, completion: int = 0) -> Usage:
    return Usage(prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion)


def estimate_cost(model: str, usage: Usage, pricing: dict[str, dict[str, float]]) -> float | None:
    rates = pricing.get(model)
    if not rates:
        return None
    inp = float(rates.get("input", 0))
    out = float(rates.get("output", 0))
    return (usage.prompt_tokens * inp + usage.completion_tokens * out) / 1_000_000
