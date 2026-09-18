"""API-key storage backed by the OS credential vault via keyring."""

from __future__ import annotations

import os

SERVICE_NAME = "StoryFactory"
PROVIDER_ENV = {
    "openai": "OPENAI_API_KEY",
    "openai_compat": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
}


def _keyring():
    try:
        import keyring
    except ImportError as exc:
        raise RuntimeError("安全凭据组件未安装，请安装 desktop 依赖。") from exc
    return keyring


def store_api_key(provider: str, secret: str) -> str:
    env_name = PROVIDER_ENV.get(provider.strip().lower(), "")
    if not env_name:
        raise ValueError("该 Provider 不需要或不支持保存密钥")
    value = secret.strip()
    if not value:
        raise ValueError("API Key 不能为空")
    _keyring().set_password(SERVICE_NAME, env_name, value)
    os.environ[env_name] = value
    return env_name


def delete_api_key(provider: str) -> None:
    env_name = PROVIDER_ENV.get(provider.strip().lower(), "")
    if not env_name:
        return
    try:
        _keyring().delete_password(SERVICE_NAME, env_name)
    except Exception:
        pass
    os.environ.pop(env_name, None)


def load_keys_into_environment() -> None:
    try:
        keyring = _keyring()
    except RuntimeError:
        return
    for env_name in sorted(set(PROVIDER_ENV.values())):
        if os.environ.get(env_name):
            continue
        try:
            value = keyring.get_password(SERVICE_NAME, env_name)
        except Exception:
            continue
        if value:
            os.environ[env_name] = value

