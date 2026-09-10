"""Models page mapping. Core ProviderStatus in; display rows out."""

from __future__ import annotations

from dataclasses import dataclass

from factory.models.specs import known_provider_ids, provider_label
from factory.models.types import ModelProfile
from factory.service import ProviderStatus


@dataclass(frozen=True)
class ProviderRow:
    name: str
    display_name: str
    state: str
    env_hint: str
    enabled: bool
    configured: bool


@dataclass(frozen=True)
class ProfileAdvanced:
    profile_id: str
    provider: str
    model: str
    display_name: str
    temperature: float
    timeout_sec: int
    max_tokens: int
    max_retries: int
    base_url: str
    api_key_env: str
    key_configured: bool


def ordered_provider_statuses(rows: tuple[ProviderStatus, ...]) -> tuple[ProviderStatus, ...]:
    rank = {name: i for i, name in enumerate(known_provider_ids())}
    return tuple(sorted(rows, key=lambda row: (rank.get(row.name, 99), row.name)))


def build_provider_row(status: ProviderStatus) -> ProviderRow:
    if not status.env_names:
        state = "Not required"
    else:
        state = "Configured" if status.configured else "Missing"
    if not status.enabled:
        state = f"{state} · disabled"
    return ProviderRow(
        name=status.name,
        display_name=provider_label(status.name),
        state=state,
        env_hint=" or ".join(status.env_names) if status.env_names else "—",
        enabled=status.enabled,
        configured=status.configured,
    )


def ordered_provider_rows(rows: tuple[ProviderStatus, ...]) -> tuple[ProviderRow, ...]:
    return tuple(build_provider_row(item) for item in ordered_provider_statuses(rows))


def build_profile_advanced(spec: ModelProfile, configured: bool) -> ProfileAdvanced:
    env_name = spec.api_key_env or ""
    return ProfileAdvanced(
        profile_id=spec.name,
        provider=spec.provider,
        model=spec.model,
        display_name=spec.display_name or spec.name,
        temperature=spec.temperature,
        timeout_sec=spec.timeout_sec,
        max_tokens=spec.max_tokens,
        max_retries=spec.max_retries,
        base_url=spec.base_url or "",
        api_key_env=env_name,
        key_configured=configured,
    )
