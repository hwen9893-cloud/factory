"""Vendor providers. Official SDKs stay in this module; agents never import them."""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from factory.models.jsonutil import parse_json_object
from factory.models.keys import key_hint, read_key
from factory.models.mock_data import MOCK_STRUCTURED
from factory.models.specs import (
    BACKEND_ANTHROPIC,
    BACKEND_GEMINI,
    BACKEND_MOCK,
    BACKEND_OPENAI_COMPAT,
    default_base_url,
    get_spec,
)
from factory.models.types import GenerationConfig, GenerationResult, ModelProfile, usage_from_counts


class ProviderError(RuntimeError):
    """Non-retryable provider failure (auth, bad request, missing SDK, empty output)."""


class RetryableError(ProviderError):
    """Timeout, 429, or 5xx. ModelClient backs off and retries."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class Provider(ABC):
    """One vendor backend. Return GenerationResult; do not retry here."""

    name: str = "provider"

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        config: GenerationConfig,
        json_mode: bool = False,
    ) -> GenerationResult:
        """Run one chat completion."""

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        config: GenerationConfig,
        json_mode: bool = False,
        on_token: Callable[[str], None] | None = None,
    ) -> GenerationResult:
        """Yield tokens through on_token, then return the same result as complete().

        Default: one-shot complete() and a single on_token call with the full text.
        """
        result = self.complete(messages, model=model, config=config, json_mode=json_mode)
        if on_token and result.text:
            on_token(result.text)
        return result

    def complete_structured(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        config: GenerationConfig,
        schema: dict[str, Any],
        purpose: str = "",
    ) -> dict[str, Any]:
        instructed = list(messages) + [
            {
                "role": "user",
                "content": "Respond with a single JSON object only. No markdown. Schema:\n"
                + json.dumps(schema, ensure_ascii=False),
            }
        ]
        result = self.complete(instructed, model=model, config=config, json_mode=True)
        try:
            return parse_json_object(result.text)
        except ValueError as exc:
            raise ProviderError(f"{self.name} returned non-JSON output") from exc


def _split_system(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
    system_parts = [m["content"] for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    return "\n\n".join(system_parts), rest


class OpenAIProvider(Provider):
    """OpenAI Python SDK. Also used for OpenRouter, Qwen/DashScope, and any OpenAI-compatible base_url."""

    def __init__(self, api_key: str, base_url: str, *, name: str = "openai") -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ProviderError("OpenAI SDK missing. pip install openai") from exc
        if not api_key:
            raise ProviderError(f"empty API key for provider {name}. Set the env var listed in config.")
        headers = {}
        if "openrouter.ai" in base_url:
            headers = {"HTTP-Referer": "https://local.novel-factory", "X-Title": "novel-factory"}
        self.name = name
        self.base_url = base_url.rstrip("/")
        self._client = OpenAI(
            api_key=api_key,
            base_url=self.base_url,
            max_retries=0,
            default_headers=headers or None,
        )

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        config: GenerationConfig,
        json_mode: bool = False,
    ) -> GenerationResult:
        from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "timeout": config.timeout_sec,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        started = time.perf_counter()
        try:
            response = self._client.chat.completions.create(**kwargs)
        except RateLimitError as exc:
            raise RetryableError(str(exc), retry_after=_retry_after(exc)) from exc
        except (APITimeoutError, APIConnectionError, InternalServerError) as exc:
            raise RetryableError(str(exc)) from exc
        except Exception as exc:
            raise ProviderError(f"{self.name} request failed: {exc}") from exc
        choice = (response.choices or [None])[0]
        text = (choice.message.content if choice and choice.message else None) or ""
        usage = getattr(response, "usage", None)
        return GenerationResult(
            text=text,
            model=getattr(response, "model", model) or model,
            provider=self.name,
            usage=usage_from_counts(
                getattr(usage, "prompt_tokens", 0) or 0,
                getattr(usage, "completion_tokens", 0) or 0,
            ),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        config: GenerationConfig,
        json_mode: bool = False,
        on_token: Callable[[str], None] | None = None,
    ) -> GenerationResult:
        from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "timeout": config.timeout_sec,
            "stream": True,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        started = time.perf_counter()
        try:
            response = self._client.chat.completions.create(**kwargs)
        except RateLimitError as exc:
            raise RetryableError(str(exc), retry_after=_retry_after(exc)) from exc
        except (APITimeoutError, APIConnectionError, InternalServerError) as exc:
            raise RetryableError(str(exc)) from exc
        except Exception as exc:
            raise ProviderError(f"{self.name} request failed: {exc}") from exc
        parts: list[str] = []
        usage = None
        model_name = model
        for chunk in response:
            model_name = getattr(chunk, "model", None) or model_name
            usage = getattr(chunk, "usage", None) or usage
            choice = (getattr(chunk, "choices", None) or [None])[0]
            delta = getattr(choice, "delta", None) if choice is not None else None
            piece = (getattr(delta, "content", None) if delta is not None else None) or ""
            if piece:
                parts.append(piece)
                if on_token:
                    on_token(piece)
        text = "".join(parts)
        return GenerationResult(
            text=text,
            model=model_name or model,
            provider=self.name,
            usage=usage_from_counts(
                getattr(usage, "prompt_tokens", 0) or 0,
                getattr(usage, "completion_tokens", 0) or 0,
            ),
            latency_ms=(time.perf_counter() - started) * 1000,
        )


class QwenProvider(OpenAIProvider):
    """Alibaba Cloud DashScope (Tongyi Qianwen / Qwen) via OpenAI-compatible Chat Completions.

    Same rank as OpenAI / Anthropic / Gemini / OpenRouter: Workflow and Agents
    never see this class. Retry, JSON repair, and usage logging stay in ModelClient.
    Streaming uses the inherited OpenAI-compatible `stream()`.
    """

    name = "qwen"

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        if not api_key:
            raise ProviderError("empty API key for qwen. Set DASHSCOPE_API_KEY.")
        super().__init__(
            api_key,
            (base_url or default_base_url("qwen")).rstrip("/"),
            name="qwen",
        )


class AnthropicProvider(Provider):
    """Anthropic official SDK."""

    name = "anthropic"

    def __init__(self, api_key: str) -> None:
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise ProviderError("Anthropic SDK missing. pip install anthropic") from exc
        if not api_key:
            raise ProviderError("empty API key for anthropic. Set ANTHROPIC_API_KEY.")
        self._client = Anthropic(api_key=api_key, max_retries=0)

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        config: GenerationConfig,
        json_mode: bool = False,
    ) -> GenerationResult:
        from anthropic import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

        system, rest = _split_system(messages)
        payload = [{"role": m["role"], "content": m["content"]} for m in rest]
        started = time.perf_counter()
        try:
            response = self._client.messages.create(
                model=model,
                messages=payload,
                system=system or anthropic_omit(),
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                timeout=config.timeout_sec,
            )
        except RateLimitError as exc:
            raise RetryableError(str(exc), retry_after=_retry_after(exc)) from exc
        except (APITimeoutError, APIConnectionError) as exc:
            raise RetryableError(str(exc)) from exc
        except APIStatusError as exc:
            if exc.status_code >= 500:
                raise RetryableError(str(exc)) from exc
            raise ProviderError(f"anthropic HTTP {exc.status_code}: {exc}") from exc
        except Exception as exc:
            raise ProviderError(f"anthropic request failed: {exc}") from exc
        text = "".join(getattr(block, "text", "") for block in (response.content or []))
        usage = getattr(response, "usage", None)
        return GenerationResult(
            text=text,
            model=getattr(response, "model", model) or model,
            provider=self.name,
            usage=usage_from_counts(
                getattr(usage, "input_tokens", 0) or 0,
                getattr(usage, "output_tokens", 0) or 0,
            ),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        config: GenerationConfig,
        json_mode: bool = False,
        on_token: Callable[[str], None] | None = None,
    ) -> GenerationResult:
        from anthropic import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

        system, rest = _split_system(messages)
        payload = [{"role": m["role"], "content": m["content"]} for m in rest]
        started = time.perf_counter()
        try:
            with self._client.messages.stream(
                model=model,
                messages=payload,
                system=system or anthropic_omit(),
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                timeout=config.timeout_sec,
            ) as stream:
                for piece in stream.text_stream:
                    if piece and on_token:
                        on_token(piece)
                response = stream.get_final_message()
        except RateLimitError as exc:
            raise RetryableError(str(exc), retry_after=_retry_after(exc)) from exc
        except (APITimeoutError, APIConnectionError) as exc:
            raise RetryableError(str(exc)) from exc
        except APIStatusError as exc:
            if exc.status_code >= 500:
                raise RetryableError(str(exc)) from exc
            raise ProviderError(f"anthropic HTTP {exc.status_code}: {exc}") from exc
        except Exception as exc:
            raise ProviderError(f"anthropic request failed: {exc}") from exc
        text = "".join(getattr(block, "text", "") for block in (response.content or []))
        usage = getattr(response, "usage", None)
        return GenerationResult(
            text=text,
            model=getattr(response, "model", model) or model,
            provider=self.name,
            usage=usage_from_counts(
                getattr(usage, "input_tokens", 0) or 0,
                getattr(usage, "output_tokens", 0) or 0,
            ),
            latency_ms=(time.perf_counter() - started) * 1000,
        )


def anthropic_omit() -> Any:
    try:
        from anthropic import NOT_GIVEN
        return NOT_GIVEN
    except Exception:
        return None


class GeminiProvider(Provider):
    """Google Gen AI official SDK (`google-genai`)."""

    name = "gemini"

    def __init__(self, api_key: str, timeout_sec: float = 120.0) -> None:
        try:
            from google import genai
        except ImportError as exc:
            raise ProviderError("Gemini SDK missing. pip install google-genai") from exc
        if not api_key:
            raise ProviderError("empty API key for gemini. Set GEMINI_API_KEY or GOOGLE_API_KEY.")
        self._client = genai.Client(
            api_key=api_key,
            http_options={"timeout": int(timeout_sec * 1000)},
        )

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        config: GenerationConfig,
        json_mode: bool = False,
    ) -> GenerationResult:
        from google.genai import types

        system, rest = _split_system(messages)
        contents = []
        for item in rest:
            role = "model" if item.get("role") == "assistant" else "user"
            contents.append(types.Content(role=role, parts=[types.Part(text=item["content"])]))
        gen_config = types.GenerateContentConfig(
            temperature=config.temperature,
            max_output_tokens=config.max_tokens,
            system_instruction=system or None,
            response_mime_type="application/json" if json_mode else None,
        )
        started = time.perf_counter()
        try:
            response = self._client.models.generate_content(
                model=model,
                contents=contents,
                config=gen_config,
            )
        except Exception as exc:
            name = type(exc).__name__.lower()
            message = str(exc).lower()
            if "timeout" in name or "429" in message or "resource exhausted" in message or "unavailable" in message:
                raise RetryableError(str(exc)) from exc
            raise ProviderError(f"gemini request failed: {exc}") from exc
        usage_meta = getattr(response, "usage_metadata", None)
        return GenerationResult(
            text=getattr(response, "text", None) or "",
            model=model,
            provider=self.name,
            usage=usage_from_counts(
                getattr(usage_meta, "prompt_token_count", 0) or 0,
                getattr(usage_meta, "candidates_token_count", 0) or 0,
            ),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        config: GenerationConfig,
        json_mode: bool = False,
        on_token: Callable[[str], None] | None = None,
    ) -> GenerationResult:
        from google.genai import types

        system, rest = _split_system(messages)
        contents = []
        for item in rest:
            role = "model" if item.get("role") == "assistant" else "user"
            contents.append(types.Content(role=role, parts=[types.Part(text=item["content"])]))
        gen_config = types.GenerateContentConfig(
            temperature=config.temperature,
            max_output_tokens=config.max_tokens,
            system_instruction=system or None,
            response_mime_type="application/json" if json_mode else None,
        )
        started = time.perf_counter()
        try:
            chunks = self._client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=gen_config,
            )
        except Exception as exc:
            name = type(exc).__name__.lower()
            message = str(exc).lower()
            if "timeout" in name or "429" in message or "resource exhausted" in message or "unavailable" in message:
                raise RetryableError(str(exc)) from exc
            raise ProviderError(f"gemini request failed: {exc}") from exc
        parts: list[str] = []
        usage_meta = None
        try:
            for chunk in chunks:
                piece = getattr(chunk, "text", None) or ""
                if piece:
                    parts.append(piece)
                    if on_token:
                        on_token(piece)
                usage_meta = getattr(chunk, "usage_metadata", None) or usage_meta
        except Exception as exc:
            name = type(exc).__name__.lower()
            message = str(exc).lower()
            if "timeout" in name or "429" in message or "resource exhausted" in message or "unavailable" in message:
                raise RetryableError(str(exc)) from exc
            raise ProviderError(f"gemini request failed: {exc}") from exc
        return GenerationResult(
            text="".join(parts),
            model=model,
            provider=self.name,
            usage=usage_from_counts(
                getattr(usage_meta, "prompt_token_count", 0) or 0,
                getattr(usage_meta, "candidates_token_count", 0) or 0,
            ),
            latency_ms=(time.perf_counter() - started) * 1000,
        )


class MockProvider(Provider):
    """Deterministic backend for tests and offline runs. No network, no SDK."""

    name = "mock"

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        config: GenerationConfig,
        json_mode: bool = False,
    ) -> GenerationResult:
        started = time.perf_counter()
        blob = "\n".join(m.get("content", "") for m in messages)
        hero = "陆沉" if "陆沉" in blob else "主角"
        rival = "赵衡" if "赵衡" in blob else "对手"
        text = (
            f"{hero}站在演武场边缘，袖口压住旧伤。{rival}当众挑衅，木剑点在他脚边。\n\n"
            f"{hero}没有解释。灵气逆冲经脉，青岚剑诀递出，将挑衅者逼退七步。\n\n"
            "高台上的执事睁开眼。这一剑接下了，更大的试炼还在后面。"
        )
        inp = max(0, (len(blob) + 1) // 2)
        out = max(0, (len(text) + 1) // 2)
        return GenerationResult(
            text=text,
            model=model,
            provider=self.name,
            usage=usage_from_counts(inp, out),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        config: GenerationConfig,
        json_mode: bool = False,
        on_token: Callable[[str], None] | None = None,
    ) -> GenerationResult:
        result = self.complete(messages, model=model, config=config, json_mode=json_mode)
        if on_token and result.text:
            for piece in _chunks(result.text, 24):
                on_token(piece)
        return result

    def complete_structured(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        config: GenerationConfig,
        schema: dict[str, Any],
        purpose: str = "",
    ) -> dict[str, Any]:
        payload = MOCK_STRUCTURED.get(purpose)
        if payload is None and purpose in {"novel_plan", "outline"}:
            payload = MOCK_STRUCTURED["outline"]
        if payload is None:
            return {"status": "mock", "purpose": purpose, "schema_keys": list(schema.keys())}
        return json.loads(json.dumps(payload))


class MockModelProvider(MockProvider):
    """Programmable mock: fixed JSON/text for a prompt needle or purpose. No network."""

    def __init__(
        self,
        *,
        by_prompt: dict[str, Any] | None = None,
        by_purpose: dict[str, Any] | None = None,
        default_text: str | None = None,
    ) -> None:
        self.by_prompt = {str(key): value for key, value in dict(by_prompt or {}).items() if str(key)}
        self.by_purpose = dict(by_purpose or {})
        self.default_text = default_text
        self.call_count = 0

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        config: GenerationConfig,
        json_mode: bool = False,
    ) -> GenerationResult:
        self.call_count += 1
        started = time.perf_counter()
        blob = "\n".join(item.get("content") or "" for item in messages)
        matched = self._match_prompt(blob)
        if matched is None and self.default_text is not None:
            matched = self.default_text
        if matched is None:
            return super().complete(messages, model=model, config=config, json_mode=json_mode)
        text = matched if isinstance(matched, str) else json.dumps(matched, ensure_ascii=False)
        inp = max(0, (len(blob) + 1) // 2)
        out = max(0, (len(text) + 1) // 2)
        return GenerationResult(
            text=text,
            model=model,
            provider=self.name,
            usage=usage_from_counts(inp, out),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    def complete_structured(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        config: GenerationConfig,
        schema: dict[str, Any],
        purpose: str = "",
    ) -> dict[str, Any]:
        self.call_count += 1
        if purpose in self.by_purpose:
            return json.loads(json.dumps(self.by_purpose[purpose]))
        blob = "\n".join(item.get("content") or "" for item in messages)
        matched = self._match_prompt(blob)
        if isinstance(matched, dict):
            return json.loads(json.dumps(matched))
        if isinstance(matched, str):
            return parse_json_object(matched)
        return super().complete_structured(
            messages, model=model, config=config, schema=schema, purpose=purpose
        )

    def _match_prompt(self, blob: str) -> Any:
        for needle, payload in self.by_prompt.items():
            if needle in blob:
                return payload
        return None


def _chunks(text: str, size: int) -> list[str]:
    if size <= 0:
        return [text] if text else []
    return [text[index : index + size] for index in range(0, len(text), size)]


def _retry_after(exc: BaseException) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or {}
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _read_key(env_name: str, provider: str) -> str:
    return read_key(provider, env_name)


def build_provider(profile: ModelProfile) -> Provider:
    """Construct a provider from a profile. API keys come from the environment."""
    name = profile.provider.strip().lower()
    spec = get_spec(name)
    if spec is None:
        raise ProviderError(f"unknown provider {profile.provider!r}")
    if spec.backend == BACKEND_MOCK:
        return MockProvider()
    key = _read_key(profile.api_key_env, name)
    if not key:
        hint = key_hint(name, profile.api_key_env) or "the provider API key env var"
        raise ProviderError(f"missing API key for {name}. Set {hint}.")
    if spec.backend == BACKEND_OPENAI_COMPAT:
        fallback = spec.base_url or default_base_url("openai")
        base = (profile.base_url or fallback).rstrip("/")
        if name == "qwen":
            return QwenProvider(key, base)
        return OpenAIProvider(key, base, name=name)
    if spec.backend == BACKEND_ANTHROPIC:
        return AnthropicProvider(key)
    if spec.backend == BACKEND_GEMINI:
        return GeminiProvider(key, timeout_sec=float(profile.timeout_sec))
    raise ProviderError(f"unknown provider {profile.provider!r}")
