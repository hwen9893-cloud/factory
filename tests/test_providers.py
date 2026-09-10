"""Provider registry and mock / structured JSON helpers."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from factory.models.jsonutil import parse_json_object
from factory.models.providers import MockProvider, ProviderError, build_provider
from factory.models.types import GenerationConfig, ModelProfile


def _profile(provider: str, **kwargs) -> ModelProfile:
    return ModelProfile(name="t", provider=provider, model="test-model", **kwargs)


class ProviderTest(unittest.TestCase):
    def test_mock_complete_and_structured(self) -> None:
        provider = build_provider(_profile("mock"))
        result = provider.complete(
            [{"role": "user", "content": "请写陆沉与赵衡"}],
            model="mock",
            config=GenerationConfig(),
        )
        self.assertIn("陆沉", result.text)
        outline = provider.complete_structured(
            [{"role": "user", "content": "大纲"}],
            model="mock",
            config=GenerationConfig(),
            schema={"title": "string"},
            purpose="outline",
        )
        self.assertIn("volumes", outline)

    def test_unknown_provider(self) -> None:
        with self.assertRaises(ProviderError):
            build_provider(_profile("not-a-vendor"))

    def test_openai_requires_key(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            with self.assertRaises(ProviderError):
                build_provider(_profile("openai", api_key_env="OPENAI_API_KEY"))

    def test_openrouter_uses_official_openai_sdk_wrapper(self) -> None:
        try:
            import openai  # noqa: F401
        except ImportError:
            self.skipTest("openai sdk not installed")
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}, clear=False):
            provider = build_provider(_profile("openrouter", api_key_env="OPENROUTER_API_KEY"))
        self.assertEqual(provider.name, "openrouter")
        self.assertEqual(provider.base_url, "https://openrouter.ai/api/v1")

    def test_parse_fenced_json(self) -> None:
        payload = parse_json_object("```json\n{\"ok\": true}\n```")
        self.assertEqual(payload, {"ok": True})

    def test_mock_provider_type(self) -> None:
        self.assertIsInstance(build_provider(_profile("mock")), MockProvider)


if __name__ == "__main__":
    unittest.main()
