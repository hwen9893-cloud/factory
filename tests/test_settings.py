"""Config loading tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory.settings import discover_project_config, load_settings


def _isolate_env(**extra: str):
    wiped = {key: "" for key in os.environ if key.startswith("FACTORY_")}
    wiped.update(extra)
    return patch.dict(os.environ, wiped, clear=False)


class SettingsTest(unittest.TestCase):
    def test_loads_yaml_and_defaults_to_mock(self) -> None:
        with patch("factory.settings.discover_project_config", return_value=None), _isolate_env():
            settings = load_settings()
        self.assertIn("architect", settings.profiles)
        self.assertIn("planner", settings.profiles)
        self.assertIn("writer", settings.profiles)
        self.assertIn("reviewer", settings.profiles)
        self.assertEqual(settings.profile("plan").name, "planner")
        self.assertEqual(settings.profile("write").name, "writer")
        self.assertEqual(settings.profile("architect").name, "architect")
        self.assertEqual(settings.workflow[0], "world_builder")
        self.assertEqual(settings.workflow[-1], "memory")
        self.assertEqual(settings.workflows["chapter"][0], "chapter_planner")
        self.assertEqual(settings.language, "zh-CN")
        self.assertEqual(settings.chapter_target_words, 5000)
        self.assertEqual(settings.max_revisions, 2)
        self.assertEqual(settings.memory_backend, "json")
        self.assertEqual(settings.profiles["writer"].model, "writer")
        self.assertEqual(settings.profiles["writer"].provider, "mock")

    def test_env_overrides_provider(self) -> None:
        with patch("factory.settings.discover_project_config", return_value=None), _isolate_env(FACTORY_PROVIDER="openai"):
            settings = load_settings()
        self.assertEqual(settings.provider, "openai")
        self.assertEqual(settings.profiles["writer"].provider, "openai")
        self.assertEqual(settings.profiles["architect"].provider, "openai")
        self.assertEqual(settings.profiles["writer"].api_key_env, "OPENAI_API_KEY")

    def test_project_config_overlays_default(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "factory.yaml"
            path.write_text(
                "workflow: [outline]\n"
                "generation:\n  chapter_target_words: 1200\n"
                "models:\n  writer:\n    provider: anthropic\n    model: claude-test\n",
                encoding="utf-8",
            )
            with _isolate_env():
                settings = load_settings(path)
        self.assertEqual(settings.workflow, ("outline",))
        self.assertEqual(settings.chapter_target_words, 1200)
        self.assertEqual(settings.profiles["writer"].provider, "anthropic")
        self.assertEqual(settings.profiles["writer"].model, "claude-test")
        self.assertEqual(settings.profiles["planner"].provider, "mock")
        self.assertEqual(settings.max_revisions, 2)

    def test_env_overrides_project_config(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "factory.yaml"
            path.write_text("generation:\n  chapter_target_words: 1000\n", encoding="utf-8")
            with _isolate_env(FACTORY_CHAPTER_TARGET_WORDS="2000"):
                settings = load_settings(path)
        self.assertEqual(settings.chapter_target_words, 2000)

    def test_cli_overrides_env(self) -> None:
        with patch("factory.settings.discover_project_config", return_value=None), _isolate_env(
            FACTORY_PROVIDER="openai",
            FACTORY_CHAPTER_TARGET_WORDS="2000",
        ):
            settings = load_settings(
                overrides={
                    "provider": "mock",
                    "generation": {"chapter_target_words": 3000},
                }
            )
        self.assertEqual(settings.provider, "mock")
        self.assertEqual(settings.profiles["writer"].provider, "mock")
        self.assertEqual(settings.chapter_target_words, 3000)

    def test_architect_falls_back_to_planner(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "cfg.yaml"
            path.write_text("models:\n  architect: {}\n", encoding="utf-8")
            with _isolate_env():
                settings = load_settings(path)
        self.assertEqual(settings.profile("architect").name, "architect")

    def test_missing_architect_uses_planner(self) -> None:
        from factory.models.types import ModelProfile
        from factory.settings import Settings

        settings = Settings(
            provider="mock",
            data_dir=Path("."),
            default_book="demo",
            workflow=(),
            recent_chapters=1,
            prev_tail_chars=10,
            profiles={"planner": ModelProfile("planner", "mock", "mock-plan")},
        )
        self.assertEqual(settings.profile("architect").name, "planner")

    def test_discover_explicit_path_wins(self) -> None:
        path = Path("/tmp/does-not-need-to-exist.yaml")
        self.assertEqual(discover_project_config(path), path)


if __name__ == "__main__":
    unittest.main()
