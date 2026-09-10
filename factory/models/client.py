"""ModelClient: the only model API agents may call.

Retry, backoff, usage/cost logging, and JSON repair live here — not in agents.
"""

from __future__ import annotations

import json
import logging
import random
import time
from typing import Any, Protocol

from factory.models.jsonutil import parse_json_object
from factory.models.providers import MockProvider, Provider, ProviderError, RetryableError, build_provider
from factory.models.types import (
    GenerationConfig,
    GenerationResult,
    ModelProfile,
    Usage,
    estimate_cost,
)
from factory.models.usage import UsageRecord, UsageStore, now_timestamp


class ModelSettings(Protocol):
    """Settings surface the client needs. Avoids importing factory.settings."""

    pricing: dict[str, dict[str, float]]

    def profile(self, name: str) -> ModelProfile: ...

logger = logging.getLogger("factory.models")


class ModelClient:
    """Route generate / generate_structured through a named ModelProfile."""

    def __init__(
        self,
        settings: ModelSettings,
        *,
        usage_store: UsageStore | None = None,
        book_id: str = "",
    ) -> None:
        self.settings = settings
        self.usage_store = usage_store
        self.book_id = book_id
        self.last_result: GenerationResult | None = None
        self._providers: dict[str, Provider] = {}

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        profile: str = "writer",
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        agent: str = "",
    ) -> str:
        result = self._complete(
            messages,
            profile=profile,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=False,
            agent=agent,
        )
        return result.text

    def generate_structured(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        *,
        profile: str = "planner",
        purpose: str = "",
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        agent: str = "",
    ) -> dict[str, Any]:
        spec = self.settings.profile(profile)
        provider = self._provider(spec)
        config = self._config(spec, temperature=temperature, max_tokens=max_tokens)
        agent_name = agent or spec.name

        if isinstance(provider, MockProvider):
            started = time.perf_counter()
            payload = provider.complete_structured(
                messages,
                model=model or spec.model,
                config=config,
                schema=schema,
                purpose=purpose,
            )
            usage = _estimate_usage(messages, json.dumps(payload, ensure_ascii=False))
            result = GenerationResult(
                text="",
                model=model or spec.model,
                provider="mock",
                usage=usage,
                latency_ms=(time.perf_counter() - started) * 1000,
                cost_usd=estimate_cost(model or spec.model, usage, self.settings.pricing),
            )
            self.last_result = result
            self._record(spec=spec, result=result, agent=agent_name, success=True, retry_count=0)
            logger.info("structured profile=%s provider=mock purpose=%s", spec.name, purpose or "-")
            return payload

        instructed = list(messages) + [
            {
                "role": "user",
                "content": "Respond with a single JSON object only. No markdown. Schema:\n"
                + json.dumps(schema, ensure_ascii=False),
            }
        ]
        last_error: Exception | None = None
        attempts = spec.max_retries + 1
        for attempt in range(attempts):
            try:
                result = self._complete(
                    instructed,
                    profile=profile,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=True,
                    agent=agent_name,
                )
                payload = parse_json_object(result.text)
                logger.info(
                    "structured profile=%s provider=%s model=%s purpose=%s tokens=%s attempt=%s",
                    spec.name,
                    result.provider,
                    result.model,
                    purpose or "-",
                    result.usage.total_tokens,
                    attempt + 1,
                )
                return payload
            except ValueError as exc:
                last_error = exc
                logger.warning("json parse failed profile=%s attempt=%s", spec.name, attempt + 1)
                self._sleep(spec, attempt, None)
        raise ProviderError(f"JSON parsing failed after {attempts} attempt(s): {last_error}") from last_error

    def _complete(
        self,
        messages: list[dict[str, str]],
        *,
        profile: str,
        model: str | None,
        temperature: float | None,
        max_tokens: int | None,
        json_mode: bool,
        agent: str = "",
    ) -> GenerationResult:
        spec = self.settings.profile(profile)
        provider = self._provider(spec)
        config = self._config(spec, temperature=temperature, max_tokens=max_tokens)
        chosen_model = model or spec.model
        agent_name = agent or spec.name
        last_error: Exception | None = None
        attempts = spec.max_retries + 1
        for attempt in range(attempts):
            try:
                result = provider.complete(
                    messages,
                    model=chosen_model,
                    config=config,
                    json_mode=json_mode,
                )
                result.attempts = attempt + 1
                result.cost_usd = estimate_cost(result.model, result.usage, self.settings.pricing)
                self.last_result = result
                self._record(spec=spec, result=result, agent=agent_name, success=True, retry_count=attempt)
                logger.info(
                    "generate profile=%s provider=%s model=%s tokens=%s latency_ms=%.0f cost=%s attempt=%s",
                    spec.name,
                    result.provider,
                    result.model,
                    result.usage.total_tokens,
                    result.latency_ms,
                    result.cost_usd,
                    result.attempts,
                )
                return result
            except RetryableError as exc:
                last_error = exc
                logger.warning("retryable error profile=%s attempt=%s err=%s", spec.name, attempt + 1, exc)
                self._sleep(spec, attempt, exc.retry_after)
            except ProviderError:
                self._record_failure(
                    spec=spec,
                    model=chosen_model,
                    agent=agent_name,
                    retry_count=attempt,
                )
                raise
        self._record_failure(
            spec=spec,
            model=chosen_model,
            agent=agent_name,
            retry_count=max(attempts - 1, 0),
        )
        raise ProviderError(f"generate failed after {attempts} attempt(s): {last_error}") from last_error

    def _record(
        self,
        *,
        spec: ModelProfile,
        result: GenerationResult,
        agent: str,
        success: bool,
        retry_count: int,
    ) -> None:
        if self.usage_store is None:
            return
        try:
            self.usage_store.record(
                UsageRecord(
                    timestamp=now_timestamp(),
                    agent=agent or spec.name,
                    provider=result.provider or spec.provider,
                    model=result.model or spec.model,
                    input_tokens=result.usage.prompt_tokens,
                    output_tokens=result.usage.completion_tokens,
                    total_tokens=result.usage.total_tokens or (
                        result.usage.prompt_tokens + result.usage.completion_tokens
                    ),
                    latency=round(result.latency_ms, 1),
                    success=success,
                    retry_count=retry_count,
                    estimated_cost=result.cost_usd,
                    book_id=self.book_id,
                )
            )
        except Exception:
            logger.warning("usage record failed profile=%s", spec.name)

    def _record_failure(self, *, spec: ModelProfile, model: str, agent: str, retry_count: int) -> None:
        empty = GenerationResult(text="", model=model, provider=spec.provider, usage=Usage())
        self._record(spec=spec, result=empty, agent=agent, success=False, retry_count=retry_count)

    def _config(
        self,
        spec: ModelProfile,
        *,
        temperature: float | None,
        max_tokens: int | None,
    ) -> GenerationConfig:
        return GenerationConfig(
            temperature=spec.temperature if temperature is None else temperature,
            max_tokens=spec.max_tokens if max_tokens is None else max_tokens,
            timeout_sec=float(spec.timeout_sec),
        )

    def _provider(self, spec: ModelProfile) -> Provider:
        key = f"{spec.provider}:{spec.base_url}:{spec.api_key_env}"
        if key not in self._providers:
            self._providers[key] = build_provider(spec)
        return self._providers[key]

    def _sleep(self, spec: ModelProfile, attempt: int, retry_after: float | None) -> None:
        if attempt >= spec.max_retries:
            return
        if retry_after is not None:
            delay = retry_after
        else:
            delay = spec.retry_backoff_sec * (2**attempt)
        if delay <= 0:
            return
        delay = min(delay, 30.0) + random.uniform(0, 0.25)
        time.sleep(delay)


def _estimate_usage(messages: list[dict[str, str]], output: str) -> Usage:
    prompt = "".join(item.get("content") or "" for item in messages)
    inp = max(0, (len(prompt) + 1) // 2)
    out = max(0, (len(output) + 1) // 2)
    return Usage(prompt_tokens=inp, completion_tokens=out, total_tokens=inp + out)
