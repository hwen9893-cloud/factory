"""SelectBox mapping over ModelRegistry. Core DTO in, labels out — no assignment writes."""

from __future__ import annotations

from factory.models.registry import ModelRegistry, ROLE_AGENTS, agents_for_role
from factory.models.types import ModelProfile

# ui.select cannot store None; this sentinel maps to Core "no override".
INHERIT_VALUE = "__default__"
INHERIT_LABEL = "Inherit Default"

ROLE_LABELS: dict[str, str] = {
    "architect": "Architect",
    "planner": "Planner",
    "writer": "Writer",
    "reviewer": "Reviewer",
}


def profile_label(registry: ModelRegistry, name: str) -> str:
    if not name:
        return "—"
    try:
        spec = registry.get_model(name)
    except KeyError:
        return name
    return spec.display_name or spec.name


def agent_role(agent: str) -> str:
    for role, agents in ROLE_AGENTS.items():
        if agent in agents:
            return role
    return ""


def role_assigned_profile(registry: ModelRegistry, role: str) -> str:
    names = [registry.assigned_model_name(agent) for agent in agents_for_role(role)]
    if not names:
        return registry.default_model
    return names[0]


def role_inherits_default(registry: ModelRegistry, role: str) -> bool:
    """True when no agent in the group has an override (Core: agent not in agent_overrides)."""
    agents = agents_for_role(role)
    return bool(agents) and not any(registry.is_override(agent) for agent in agents)


def build_model_options(
    registry: ModelRegistry,
    *,
    agent: str = "",
    role: str = "",
) -> dict[str, str]:
    """Catalog profile id → display_name for a Select.

    `ModelProfile.roles` is catalog metadata. Empty roles means visible to every agent.
    """
    return {spec.name: spec.display_name or spec.name for spec in _filtered_profiles(registry, agent=agent, role=role)}


def build_role_options(registry: ModelRegistry, role: str) -> dict[str, str]:
    default_id = registry.default_model
    inherited = f"{INHERIT_LABEL} ({profile_label(registry, default_id)})" if default_id else INHERIT_LABEL
    options: dict[str, str] = {INHERIT_VALUE: inherited}
    options.update(build_model_options(registry, role=role))
    current = role_assigned_profile(registry, role)
    if current and current not in options:
        options[current] = profile_label(registry, current)
    return options


def _filtered_profiles(
    registry: ModelRegistry,
    *,
    agent: str = "",
    role: str = "",
) -> tuple[ModelProfile, ...]:
    wanted = role.strip()
    include = ""
    if agent:
        wanted = agent_role(agent)
        include = registry.assigned_model_name(agent)
    elif wanted:
        include = role_assigned_profile(registry, wanted) or registry.default_model
    enabled = registry.list_models(enabled_only=True)
    if not wanted:
        return enabled
    rows = [
        spec
        for spec in enabled
        if (not spec.roles) or wanted in spec.roles or spec.name == wanted
    ]
    names = {spec.name for spec in rows}
    extra = include or registry.default_model
    if extra and extra not in names:
        try:
            rows = [registry.get_model(extra), *rows]
        except KeyError:
            pass
    return tuple(rows)
