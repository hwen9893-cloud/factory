"""Lightweight model catalog. Lookup and mapping only — no HTTP, no plugins."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from factory.models.keys import key_configured
from factory.models.specs import default_base_url, default_key_env, known_provider_ids
from factory.models.types import ModelProfile, resolve_profile_name

# Fallback when YAML `agents:` omits a step. Matches BaseAgent.model class attributes.
AGENT_DEFAULT_MODELS: dict[str, str] = {
    "world_builder": "architect",
    "character": "architect",
    "novel_architect": "architect",
    "outline": "planner",
    "volume_planner": "planner",
    "chapter_planner": "planner",
    "chapter_writer": "writer",
    "continuity": "reviewer",
    "reviewer": "reviewer",
    "revision": "writer",
    "memory": "reviewer",
}

# Assignment groups: one catalog key applies to every agent in the group.
# Display names for these groups are not part of the registry.
ROLE_AGENTS: dict[str, tuple[str, ...]] = {
    "architect": ("world_builder", "character", "novel_architect"),
    "planner": ("outline", "volume_planner", "chapter_planner"),
    "writer": ("chapter_writer", "revision"),
    "reviewer": ("continuity", "reviewer", "memory"),
}


@dataclass(frozen=True)
class ProviderInfo:
    """One vendor entry from YAML `providers:`. Not an SDK client."""

    name: str
    enabled: bool = True
    api_key_env: str = ""
    base_url: str = ""


class ModelRegistry:
    """Named profiles, providers, and agent assignment resolution.

    Does not build dropdowns, labels, or inherit copy. Callers read
    ModelProfile.display_name and is_override() themselves.
    """

    def __init__(
        self,
        *,
        profiles: dict[str, ModelProfile],
        providers: dict[str, ProviderInfo],
        agent_models: dict[str, str],
        lookup: Callable[[str], ModelProfile] | None = None,
        default_model: str = "",
        agent_overrides: dict[str, str] | None = None,
    ) -> None:
        self.profiles = profiles
        self.providers = providers
        self.agent_models = agent_models
        self.default_model = (default_model or "").strip()
        self.agent_overrides = dict(agent_overrides or {})
        self._lookup = lookup

    @classmethod
    def from_settings(cls, settings: Any) -> ModelRegistry:
        return cls(
            profiles=dict(settings.profiles),
            providers=dict(settings.providers),
            agent_models=dict(settings.agent_models),
            lookup=settings.profile,
            default_model=str(getattr(settings, "default_model", "") or ""),
            agent_overrides=dict(getattr(settings, "agent_overrides", {}) or {}),
        )

    def list_providers(self) -> tuple[ProviderInfo, ...]:
        return tuple(self.providers[name] for name in sorted(self.providers))

    def list_models(self, *, enabled_only: bool = True) -> tuple[ModelProfile, ...]:
        rows = []
        for name in sorted(self.profiles):
            spec = self.profiles[name]
            if enabled_only and not self._provider_enabled(spec.provider):
                continue
            rows.append(spec)
        return tuple(rows)

    def get_model(self, name: str) -> ModelProfile:
        if self._lookup is not None:
            return self._lookup(name)
        key = resolve_profile_name(name)
        if key in self.profiles:
            return self.profiles[key]
        if name in self.profiles:
            return self.profiles[name]
        raise KeyError(f"unknown model: {name}")

    def get_provider(self, name: str) -> ProviderInfo:
        key = name.strip().lower()
        if key in self.providers:
            return self.providers[key]
        raise KeyError(f"unknown provider: {name}")

    def assigned_model_name(self, agent: str, default: str = "") -> str:
        if agent in self.agent_overrides:
            return self.agent_overrides[agent]
        if self.default_model:
            return self.default_model
        mapped = self.agent_models.get(agent)
        if mapped:
            return mapped
        if default:
            return default
        return AGENT_DEFAULT_MODELS.get(agent, agent)

    def is_override(self, agent: str) -> bool:
        """True when this agent has an explicit catalog key (does not inherit default_model)."""
        return agent in self.agent_overrides

    def resolve_agent_model(self, agent: str, default: str = "") -> ModelProfile:
        return self.get_model(self.assigned_model_name(agent, default=default))

    def _provider_enabled(self, name: str) -> bool:
        info = self.providers.get(name.strip().lower())
        if info is None:
            return True
        return info.enabled


def format_registry(registry: ModelRegistry) -> str:
    """Plain-text listing for `factory models`."""
    lines = ["default"]
    if registry.default_model:
        try:
            spec = registry.get_model(registry.default_model)
            lines.append(f"  {registry.default_model}  ({spec.provider} / {spec.model})")
        except KeyError:
            lines.append(f"  {registry.default_model}  (missing)")
    else:
        lines.append("  —")
    lines.append("")
    lines.append("providers")
    providers = registry.list_providers()
    if not providers:
        lines.append("  —")
    else:
        width = max(len(item.name) for item in providers)
        width = max(width, 8)
        for item in providers:
            mark = "on" if item.enabled else "off"
            if not item.api_key_env:
                key_state = "n/a"
            else:
                key_state = "configured" if key_configured(item.name, item.api_key_env) else "missing"
            extra = f"  {item.api_key_env}" if item.api_key_env else ""
            lines.append(f"  {item.name:<{width}}  {mark}  {key_state}{extra}")

    lines.append("")
    lines.append("models")
    models = registry.list_models(enabled_only=False)
    enabled_names = {item.name for item in registry.list_models(enabled_only=True)}
    if not models:
        lines.append("  —")
    else:
        name_w = max(len(item.name) for item in models)
        name_w = max(name_w, 8)
        for item in models:
            lines.append(
                f"  {item.name:<{name_w}}  {item.provider:<12}  {item.model}  {item.display_name or item.name}"
                + ("" if item.name in enabled_names else "  [hidden]")
            )

    lines.append("")
    lines.append("agents")
    agents = _agent_names(registry)
    if not agents:
        lines.append("  —")
    else:
        agent_w = max(len(name) for name in agents)
        agent_w = max(agent_w, 8)
        for agent in agents:
            key = registry.assigned_model_name(agent)
            try:
                spec = registry.get_model(key)
                mark = "override" if registry.is_override(agent) else "default"
                lines.append(
                    f"  {agent:<{agent_w}}  {key}  ({spec.provider} / {spec.model})  {mark}"
                )
            except KeyError:
                lines.append(f"  {agent:<{agent_w}}  {key}  (missing)")
    return "\n".join(lines)


def _agent_names(registry: ModelRegistry) -> list[str]:
    names = set(AGENT_DEFAULT_MODELS) | set(registry.agent_models)
    return sorted(names)


def build_provider_catalog(
    raw_providers: Any,
    profiles: Iterable[ModelProfile],
) -> dict[str, ProviderInfo]:
    """Merge YAML `providers:` with vendors that appear on model entries."""
    declared: dict[str, Any] = {}
    if isinstance(raw_providers, dict):
        declared = {str(key).strip().lower(): value for key, value in raw_providers.items()}

    names: list[str] = []
    seen: set[str] = set()
    for key in list(declared) + list(known_provider_ids()) + [spec.provider for spec in profiles]:
        name = str(key).strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)

    catalog: dict[str, ProviderInfo] = {}
    for name in names:
        spec = declared.get(name, {})
        if isinstance(spec, bool):
            enabled = spec
            extra: dict[str, Any] = {}
        elif isinstance(spec, dict):
            extra = spec
            enabled = bool(extra.get("enabled", True))
        else:
            extra = {}
            enabled = True
        catalog[name] = ProviderInfo(
            name=name,
            enabled=enabled,
            api_key_env=str(extra.get("api_key_env") or default_key_env(name) or ""),
            base_url=str(extra.get("base_url") or default_base_url(name) or ""),
        )
    return catalog


def parse_agent_overrides(raw_agents: Any) -> dict[str, str]:
    """Explicit `agents:` entries only. Missing agents inherit `default_model`."""
    mapping: dict[str, str] = {}
    if not isinstance(raw_agents, dict):
        return mapping
    for name, spec in raw_agents.items():
        if isinstance(spec, str) and spec.strip():
            mapping[str(name)] = spec.strip()
        elif isinstance(spec, dict) and spec.get("model"):
            mapping[str(name)] = str(spec["model"]).strip()
    return mapping


def resolve_agent_models(overrides: dict[str, str], default_model: str = "") -> dict[str, str]:
    resolved = dict(AGENT_DEFAULT_MODELS)
    fallback = (default_model or "").strip()
    if fallback:
        for agent in resolved:
            resolved[agent] = fallback
    resolved.update(overrides)
    return resolved


def parse_agent_models(raw_agents: Any, default_model: str = "") -> dict[str, str]:
    return resolve_agent_models(parse_agent_overrides(raw_agents), default_model)


def agents_for_role(role: str) -> tuple[str, ...]:
    return ROLE_AGENTS.get(role, ())
