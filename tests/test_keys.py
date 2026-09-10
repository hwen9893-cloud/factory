"""API key helpers never return secrets to the GUI status path."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from factory.models.keys import key_configured, key_hint, scrub_secrets


class KeyPresenceTest(unittest.TestCase):
    def test_qwen_reads_fallback_name_only(self) -> None:
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "", "QWEN_API_KEY": "sk-hidden"}, clear=False):
            self.assertTrue(key_configured("qwen", "DASHSCOPE_API_KEY"))
            self.assertIn("DASHSCOPE_API_KEY", key_hint("qwen", "DASHSCOPE_API_KEY"))
            self.assertIn("QWEN_API_KEY", key_hint("qwen", "DASHSCOPE_API_KEY"))

    def test_scrub_replaces_known_values(self) -> None:
        secret = "sk-live-secret-ABCDEF"
        with patch.dict(os.environ, {"OPENAI_API_KEY": secret}, clear=False):
            text = scrub_secrets(f"401 auth failed for {secret} Bearer {secret}")
        self.assertNotIn(secret, text)
        self.assertIn("***", text)

    def test_mock_needs_no_key(self) -> None:
        self.assertTrue(key_configured("mock"))
        self.assertEqual(key_hint("mock"), "")
