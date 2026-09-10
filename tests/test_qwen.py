"""Qwen / DashScope provider: registry, auth, OpenAI-compatible complete. No live HTTP."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory.models.client import ModelClient
from factory.models.providers import (
    ProviderError,
    QwenProvider,
    RetryableError,
    build_provider,
)
from factory.models.types import GenerationConfig, ModelProfile
from factory.settings import Settings


def _qwen_profile(**kwargs) -> ModelProfile:
    return ModelProfile(
        name="writer",
        provider="qwen",
        model="qwen-plus",
        api_key_env="DASHSCOPE_API_KEY",
        **kwargs,
    )


def _no_qwen_keys():
    return patch.dict(os.environ, {"DASHSCOPE_API_KEY": "", "QWEN_API_KEY": ""}, clear=False)


def _require_openai() -> None:
    try:
        import openai  # noqa: F401
    except ImportError:
        raise unittest.SkipTest("openai sdk not installed")


class QwenProviderTest(unittest.TestCase):
    def test_missing_key_raises(self) -> None:
        with _no_qwen_keys():
            with self.assertRaises(ProviderError) as ctx:
                build_provider(_qwen_profile())
        self.assertIn("DASHSCOPE_API_KEY", str(ctx.exception))

    def test_qwen_api_key_fallback(self) -> None:
        _require_openai()
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "", "QWEN_API_KEY": "sk-qwen-fallback"}, clear=False):
            provider = build_provider(_qwen_profile())
        self.assertIsInstance(provider, QwenProvider)
        self.assertEqual(provider.name, "qwen")

    def test_build_uses_dashscope_compatible_url(self) -> None:
        _require_openai()
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "sk-dashscope-test"}, clear=False):
            provider = build_provider(_qwen_profile())
        self.assertIsInstance(provider, QwenProvider)
        self.assertEqual(provider.name, "qwen")
        self.assertEqual(provider.base_url, "https://dashscope.aliyuncs.com/compatible-mode/v1")

    def test_custom_base_url(self) -> None:
        _require_openai()
        intl = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "sk-dashscope-test"}, clear=False):
            provider = build_provider(_qwen_profile(base_url=intl))
        self.assertEqual(provider.base_url, intl)

    def test_complete_maps_text_usage_timeout_and_json_mode(self) -> None:
        _require_openai()
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "sk-dashscope-test"}, clear=False):
            provider = build_provider(_qwen_profile())

        captured: dict = {}

        class Usage:
            prompt_tokens = 11
            completion_tokens = 7

        class Message:
            content = "青岚剑光一闪。"

        class Choice:
            message = Message()

        class Response:
            choices = [Choice()]
            model = "qwen-plus"
            usage = Usage()

        def fake_create(**kwargs):
            captured.update(kwargs)
            return Response()

        provider._client.chat.completions.create = fake_create
        result = provider.complete(
            [{"role": "system", "content": "你是作者"}, {"role": "user", "content": "写一句"}],
            model="qwen-plus",
            config=GenerationConfig(temperature=0.8, max_tokens=256, timeout_sec=45),
            json_mode=True,
        )
        self.assertEqual(result.provider, "qwen")
        self.assertEqual(result.model, "qwen-plus")
        self.assertEqual(result.text, "青岚剑光一闪。")
        self.assertEqual(result.usage.prompt_tokens, 11)
        self.assertEqual(result.usage.completion_tokens, 7)
        self.assertEqual(result.usage.total_tokens, 18)
        self.assertEqual(captured["model"], "qwen-plus")
        self.assertEqual(captured["temperature"], 0.8)
        self.assertEqual(captured["max_tokens"], 256)
        self.assertEqual(captured["timeout"], 45)
        self.assertEqual(captured["response_format"], {"type": "json_object"})
        self.assertEqual(captured["messages"][0]["role"], "system")

    def test_timeout_is_retryable(self) -> None:
        _require_openai()
        from openai import APITimeoutError

        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "sk-dashscope-test"}, clear=False):
            provider = build_provider(_qwen_profile())

        class Timeout(APITimeoutError):
            def __init__(self, *args, **kwargs) -> None:
                Exception.__init__(self, "timed out")

        def boom(**_kwargs):
            raise Timeout()

        provider._client.chat.completions.create = boom
        with self.assertRaises(RetryableError):
            provider.complete(
                [{"role": "user", "content": "hi"}],
                model="qwen-plus",
                config=GenerationConfig(),
            )

    def test_auth_error_is_not_retryable(self) -> None:
        _require_openai()
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "sk-dashscope-test"}, clear=False):
            provider = build_provider(_qwen_profile())

        def boom(**_kwargs):
            raise RuntimeError("401 invalid api key")

        provider._client.chat.completions.create = boom
        with self.assertRaises(ProviderError) as ctx:
            provider.complete(
                [{"role": "user", "content": "hi"}],
                model="qwen-plus",
                config=GenerationConfig(),
            )
        self.assertNotIsInstance(ctx.exception, RetryableError)
        self.assertIn("qwen", str(ctx.exception))

    def test_model_client_does_not_branch_on_qwen_name(self) -> None:
        """Agents/Client treat qwen like any other profile; inject mock, no HTTP."""
        settings = Settings(
            provider="qwen",
            data_dir=Path("."),
            default_book="demo",
            workflow=(),
            recent_chapters=1,
            prev_tail_chars=10,
            profiles={
                "writer": ModelProfile(
                    name="writer",
                    provider="qwen",
                    model="qwen-plus",
                    api_key_env="DASHSCOPE_API_KEY",
                    max_retries=0,
                    retry_backoff_sec=0,
                )
            },
        )
        client = ModelClient(settings)
        from factory.models.providers import MockProvider

        mock = MockProvider()
        client._providers["qwen:None:DASHSCOPE_API_KEY"] = mock
        text = client.generate([{"role": "user", "content": "陆沉"}], profile="writer", agent="chapter_writer")
        self.assertIn("陆沉", text)
        self.assertEqual(client.last_result.provider, "mock")

    def test_usage_log_has_no_api_key(self) -> None:
        from factory.models.usage import UsageStore

        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "usage.sqlite"
            settings = Settings(
                provider="qwen",
                data_dir=Path(raw),
                default_book="demo",
                workflow=(),
                recent_chapters=1,
                prev_tail_chars=10,
                profiles={
                    "writer": ModelProfile(
                        name="writer",
                        provider="qwen",
                        model="qwen-plus",
                        api_key_env="DASHSCOPE_API_KEY",
                    )
                },
            )
            store = UsageStore(path)
            client = ModelClient(settings, usage_store=store, book_id="demo")
            from factory.models.providers import MockProvider

            client._providers["qwen:None:DASHSCOPE_API_KEY"] = MockProvider()
            secret = "DASHSCOPE_LIVE_KEY_SHOULD_NOT_APPEAR"
            client.generate([{"role": "user", "content": secret}], profile="writer", agent="chapter_writer")
            blob = path.read_bytes()
            self.assertNotIn(secret.encode(), blob)
            self.assertNotIn(b"sk-dashscope", blob)
            self.assertNotIn(b"DASHSCOPE", blob)


if __name__ == "__main__":
    unittest.main()
