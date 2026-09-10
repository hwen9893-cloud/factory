"""ModelRegistry: catalog lookup, agent mapping, no live HTTP."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from factory.agents.chapter import ChapterWriterAgent
from factory.models.registry import (
    AGENT_DEFAULT_MODELS,
    ROLE_AGENTS,
    ModelRegistry,
    ProviderInfo,
    format_registry,
)
from factory.models.types import ModelProfile
from factory.settings import load_settings
from test_settings import _isolate_env


class RegistryTest(unittest.TestCase):
    def test_default_yaml_lists_providers_and_role_slots(self) -> None:
        with patch("factory.settings.discover_project_config", return_value=None), _isolate_env():
            settings = load_settings()
        registry = ModelRegistry.from_settings(settings)
        names = {item.name for item in registry.list_providers()}
        self.assertTrue({"mock", "qwen", "openai", "anthropic", "gemini"}.issubset(names))
        self.assertTrue(registry.get_provider("qwen").enabled)
        models = {item.name for item in registry.list_models()}
        self.assertEqual({"architect", "planner", "writer", "reviewer"}, models)
        self.assertEqual(registry.assigned_model_name("chapter_writer"), "writer")
        self.assertEqual(registry.default_model, "writer")
        self.assertFalse(registry.is_override("chapter_writer"))
        self.assertTrue(registry.is_override("reviewer"))
        self.assertEqual(registry.resolve_agent_model("reviewer").provider, "mock")
        spec = registry.get_model("writer")
        self.assertEqual(spec.display_name or spec.name, "Writer (mock)")

    def test_named_presets_and_agent_assignment(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "factory.yaml"
            path.write_text(
                "providers:\n"
                "  mock:\n    enabled: false\n"
                "  qwen:\n    enabled: true\n"
                "  anthropic:\n    enabled: true\n"
                "models:\n"
                "  qwen_writer:\n"
                "    provider: qwen\n"
                "    model: qwen-plus\n"
                "    display_name: Qwen Writer\n"
                "    roles: [writer]\n"
                "    temperature: 0.8\n"
                "  claude_writer:\n"
                "    provider: anthropic\n"
                "    model: claude-sonnet-4\n"
                "    display_name: Claude Writer\n"
                "    roles: [writer]\n"
                "agents:\n"
                "  chapter_writer:\n    model: qwen_writer\n"
                "  reviewer:\n    model: reviewer\n",
                encoding="utf-8",
            )
            with _isolate_env():
                settings = load_settings(path)
        registry = ModelRegistry.from_settings(settings)
        self.assertFalse(registry.get_provider("mock").enabled)
        self.assertEqual(registry.get_model("qwen_writer").model, "qwen-plus")
        self.assertEqual(registry.assigned_model_name("chapter_writer"), "qwen_writer")
        self.assertEqual(registry.resolve_agent_model("chapter_writer").provider, "qwen")
        self.assertIn("chapter_writer", ROLE_AGENTS["writer"])
        self.assertEqual(registry.get_model("qwen_writer").roles, ("writer",))
        self.assertEqual(registry.get_model("claude_writer").roles, ("writer",))
        hidden = {item.name for item in registry.list_models(enabled_only=True)}
        self.assertNotIn("writer", hidden)
        self.assertIn("qwen_writer", hidden)

    def test_agent_shorthand_string(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "factory.yaml"
            path.write_text(
                "models:\n  qwen_writer:\n    provider: qwen\n    model: qwen-plus\n"
                "agents:\n  chapter_writer: qwen_writer\n",
                encoding="utf-8",
            )
            with _isolate_env():
                settings = load_settings(path)
        self.assertEqual(settings.agent_models["chapter_writer"], "qwen_writer")
        self.assertEqual(settings.agent_models["reviewer"], AGENT_DEFAULT_MODELS["reviewer"])

    def test_disabled_provider_hidden_from_list(self) -> None:
        registry = ModelRegistry(
            profiles={
                "qwen_writer": ModelProfile(
                    "qwen_writer", "qwen", "qwen-plus", display_name="Qwen Writer", roles=("writer",)
                ),
                "gpt_writer": ModelProfile("gpt_writer", "openai", "gpt-4o-mini", roles=("writer",)),
            },
            providers={
                "qwen": ProviderInfo("qwen", enabled=True),
                "openai": ProviderInfo("openai", enabled=False),
            },
            agent_models={"chapter_writer": "qwen_writer"},
        )
        listed = [item.name for item in registry.list_models()]
        self.assertEqual(listed, ["qwen_writer"])
        self.assertEqual(registry.get_provider("openai").enabled, False)

    def test_unknown_model_and_provider(self) -> None:
        registry = ModelRegistry(profiles={}, providers={}, agent_models={})
        with self.assertRaises(KeyError):
            registry.get_model("missing")
        with self.assertRaises(KeyError):
            registry.get_provider("missing")

    def test_format_registry_mentions_sections(self) -> None:
        with patch("factory.settings.discover_project_config", return_value=None), _isolate_env():
            text = format_registry(ModelRegistry.from_settings(load_settings()))
        self.assertIn("default", text)
        self.assertIn("providers", text)
        self.assertIn("models", text)
        self.assertIn("agents", text)
        self.assertIn("chapter_writer", text)
        self.assertIn("qwen", text)

    def test_base_agent_uses_registry_assignment(self) -> None:
        registry = ModelRegistry(
            profiles={
                "writer": ModelProfile("writer", "mock", "mock-write"),
                "qwen_writer": ModelProfile("qwen_writer", "qwen", "qwen-plus"),
            },
            providers={"qwen": ProviderInfo("qwen", True), "mock": ProviderInfo("mock", True)},
            agent_models={"chapter_writer": "qwen_writer"},
            lookup=lambda name: {
                "writer": ModelProfile("writer", "mock", "mock-write"),
                "qwen_writer": ModelProfile("qwen_writer", "qwen", "qwen-plus"),
            }[name],
        )
        runtime = MagicMock()
        runtime.registry = registry
        agent = ChapterWriterAgent(runtime)
        self.assertEqual(agent.model, "writer")
        self.assertEqual(agent.profile_name(), "qwen_writer")

    def test_default_model_fills_agents_without_override(self) -> None:
        registry = ModelRegistry(
            profiles={
                "qwen_plus": ModelProfile("qwen_plus", "qwen", "qwen-plus", display_name="Qwen Plus", roles=("writer",)),
                "claude_architect": ModelProfile(
                    "claude_architect", "anthropic", "claude-sonnet-4", display_name="Claude Sonnet", roles=("architect",)
                ),
            },
            providers={"qwen": ProviderInfo("qwen", True), "anthropic": ProviderInfo("anthropic", True)},
            agent_models={"chapter_writer": "qwen_plus", "world_builder": "claude_architect"},
            default_model="qwen_plus",
            agent_overrides={"world_builder": "claude_architect", "character": "claude_architect", "novel_architect": "claude_architect"},
            lookup=lambda name: {
                "qwen_plus": ModelProfile("qwen_plus", "qwen", "qwen-plus", display_name="Qwen Plus"),
                "claude_architect": ModelProfile("claude_architect", "anthropic", "claude-sonnet-4", display_name="Claude Sonnet"),
            }[name],
        )
        self.assertEqual(registry.assigned_model_name("chapter_writer"), "qwen_plus")
        self.assertEqual(registry.assigned_model_name("revision"), "qwen_plus")
        self.assertEqual(registry.assigned_model_name("world_builder"), "claude_architect")
        self.assertFalse(registry.is_override("chapter_writer"))
        self.assertTrue(registry.is_override("world_builder"))
        spec = registry.get_model("qwen_plus")
        self.assertEqual(spec.display_name or spec.name, "Qwen Plus")


if __name__ == "__main__":
    unittest.main()
