"""Built-in provider definitions. Add OpenAI-compatible vendors here.

SDK classes stay in providers.py. This module must not import vendor SDKs.
`backend` is a string so specs stay import-safe; build_provider() maps it.
"""

from __future__ import annotations

from dataclasses import dataclass

# Construction kind in providers.build_provider(). Not a plugin entry point.
BACKEND_MOCK = "mock"
BACKEND_OPENAI_COMPAT = "openai_compat"
BACKEND_ANTHROPIC = "anthropic"
BACKEND_GEMINI = "gemini"


@dataclass(frozen=True)
class ProviderSpec:
    """What a vendor is, not how the GUI paints it."""

    id: str
    display_name: str
    env_keys: tuple[str, ...] = ()
    base_url: str = ""
    ping_model: str = ""
    backend: str = BACKEND_OPENAI_COMPAT
    stream: bool = True
    json_mode: bool = True


# Canonical order: GUI/CLI listing follows this unless they overlay their own.
PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        id="qwen",
        display_name="Qwen",
        env_keys=("DASHSCOPE_API_KEY", "QWEN_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        ping_model="qwen-plus",
        backend=BACKEND_OPENAI_COMPAT,
    ),
    ProviderSpec(
        id="openai",
        display_name="OpenAI",
        env_keys=("OPENAI_API_KEY",),
        base_url="https://api.openai.com/v1",
        ping_model="gpt-4o-mini",
        backend=BACKEND_OPENAI_COMPAT,
    ),
    ProviderSpec(
        id="openai_compat",
        display_name="OpenAI-compatible",
        env_keys=("OPENAI_API_KEY",),
        base_url="https://api.openai.com/v1",
        ping_model="gpt-4o-mini",
        backend=BACKEND_OPENAI_COMPAT,
    ),
    ProviderSpec(
        id="openrouter",
        display_name="OpenRouter",
        env_keys=("OPENROUTER_API_KEY",),
        base_url="https://openrouter.ai/api/v1",
        ping_model="openai/gpt-4o-mini",
        backend=BACKEND_OPENAI_COMPAT,
    ),
    ProviderSpec(
        id="anthropic",
        display_name="Anthropic",
        env_keys=("ANTHROPIC_API_KEY",),
        ping_model="claude-sonnet-4",
        backend=BACKEND_ANTHROPIC,
    ),
    ProviderSpec(
        id="gemini",
        display_name="Gemini",
        env_keys=("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        ping_model="gemini-2.0-flash",
        backend=BACKEND_GEMINI,
    ),
    ProviderSpec(
        id="mock",
        display_name="Mock",
        ping_model="mock",
        backend=BACKEND_MOCK,
    ),
)

_BY_ID: dict[str, ProviderSpec] = {spec.id: spec for spec in PROVIDERS}


def get_spec(provider: str) -> ProviderSpec | None:
    return _BY_ID.get((provider or "").strip().lower())


def known_provider_ids() -> tuple[str, ...]:
    return tuple(_BY_ID)


def default_key_env(provider: str) -> str:
    spec = get_spec(provider)
    if spec is None or not spec.env_keys:
        return ""
    return spec.env_keys[0]


def default_base_url(provider: str) -> str:
    spec = get_spec(provider)
    return spec.base_url if spec else ""


def ping_model(provider: str) -> str:
    spec = get_spec(provider)
    if spec is None or not spec.ping_model:
        return (provider or "").strip().lower()
    return spec.ping_model


def provider_label(provider: str) -> str:
    spec = get_spec(provider)
    if spec is None:
        return provider
    return spec.display_name
