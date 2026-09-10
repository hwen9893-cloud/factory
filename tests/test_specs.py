"""ProviderSpec is the single built-in vendor table."""

from __future__ import annotations

import unittest
from pathlib import Path

from factory.models.specs import (
    BACKEND_OPENAI_COMPAT,
    PROVIDERS,
    get_spec,
    known_provider_ids,
    provider_label,
)


class ProviderSpecTest(unittest.TestCase):
    def test_known_vendors_are_defined_once(self) -> None:
        ids = known_provider_ids()
        self.assertEqual(len(ids), len(set(ids)))
        for name in ("qwen", "openai", "openrouter", "anthropic", "gemini", "mock"):
            self.assertIn(name, ids)

    def test_qwen_carries_env_url_and_compat_backend(self) -> None:
        spec = get_spec("qwen")
        assert spec is not None
        self.assertEqual(spec.display_name, "Qwen")
        self.assertEqual(spec.env_keys[0], "DASHSCOPE_API_KEY")
        self.assertIn("QWEN_API_KEY", spec.env_keys)
        self.assertIn("compatible-mode", spec.base_url)
        self.assertEqual(spec.backend, BACKEND_OPENAI_COMPAT)
        self.assertEqual(spec.ping_model, "qwen-plus")
        self.assertEqual(provider_label("qwen"), "Qwen")

    def test_openai_compat_vendors_share_backend(self) -> None:
        for name in ("openai", "openai_compat", "openrouter", "qwen"):
            spec = get_spec(name)
            assert spec is not None
            self.assertEqual(spec.backend, BACKEND_OPENAI_COMPAT)

    def test_keys_and_types_do_not_repeat_vendor_tables(self) -> None:
        root = Path(__file__).resolve().parents[1] / "factory" / "models"
        keys = (root / "keys.py").read_text(encoding="utf-8")
        types = (root / "types.py").read_text(encoding="utf-8")
        providers = (root / "providers.py").read_text(encoding="utf-8")
        self.assertNotIn("DASHSCOPE_API_KEY", keys)
        self.assertNotIn("PING_MODELS", keys)
        self.assertNotIn("DEFAULT_KEY_ENV", keys)
        self.assertNotIn("DEFAULT_KEY_ENV", types)
        self.assertNotIn("DEFAULT_BASE_URL", types)
        self.assertNotIn('{"openai", "openai_compat", "openrouter"}', providers)
        self.assertGreater(len(PROVIDERS), 3)
