"""API key presence helpers. Never return or log secret values."""

from __future__ import annotations

import os
import re

from factory.models.specs import PROVIDERS, get_spec, provider_label

_SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_\-]{8,})|(Bearer\s+\S+)", re.I)

__all__ = [
    "env_names_for",
    "key_configured",
    "key_hint",
    "provider_label",
    "read_key",
    "scrub_secrets",
]


def env_names_for(provider: str, api_key_env: str = "") -> tuple[str, ...]:
    spec = get_spec(provider)
    documented = spec.env_keys if spec else ()
    names: list[str] = []
    seen: set[str] = set()
    for item in (api_key_env, *documented):
        name = str(item or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return tuple(names)


def key_configured(provider: str, api_key_env: str = "") -> bool:
    """True if any documented env var for this provider is non-empty. Never returns the value."""
    names = env_names_for(provider, api_key_env)
    if not names:
        return True
    return any(bool(os.environ.get(name)) for name in names)


def read_key(provider: str, api_key_env: str = "") -> str:
    """Load the key for Provider construction. Callers must not log or persist the return value."""
    for name in env_names_for(provider, api_key_env):
        value = os.environ.get(name) or ""
        if value:
            return value
    return ""


def key_hint(provider: str, api_key_env: str = "") -> str:
    names = env_names_for(provider, api_key_env)
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return " or ".join(names)


def scrub_secrets(message: str) -> str:
    """Strip known API key values and common token shapes from an error string."""
    text = str(message or "")
    for spec in PROVIDERS:
        for name in spec.env_keys:
            secret = os.environ.get(name) or ""
            if len(secret) >= 4:
                text = text.replace(secret, "***")
    return _SECRET_RE.sub("***", text)
