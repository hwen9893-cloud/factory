"""Architecture boundary: GUI may import Core; Core must not import GUI."""

from __future__ import annotations

import ast
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "factory"

CORE_IMPORT_TARGETS = (
    "factory.service",
    "factory.workflow",
    "factory.events",
    "factory.models.registry",
    "factory.models.specs",
    "factory.models.keys",
    "factory.cli",
    "factory.agents",
    "factory.demo",
    "factory.settings",
    "factory.pipeline.chapter",
)

# Tests that must keep working if factory.gui is missing.
CORE_PYTEST = (
    "tests/test_agents.py",
    "tests/test_cli.py",
    "tests/test_client.py",
    "tests/test_context.py",
    "tests/test_core.py",
    "tests/test_demo.py",
    "tests/test_keys.py",
    "tests/test_memory.py",
    "tests/test_pipeline.py",
    "tests/test_prompts.py",
    "tests/test_providers.py",
    "tests/test_qwen.py",
    "tests/test_registry.py",
    "tests/test_schema.py",
    "tests/test_settings.py",
    "tests/test_specs.py",
    "tests/test_usage.py",
    "tests/test_workflow.py",
)


def _py_files(relative: str) -> list[Path]:
    path = PKG / relative
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.py"))


def _imports_gui(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "factory.gui" or alias.name.startswith("factory.gui."):
                    hits.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "factory.gui" or node.module.startswith("factory.gui."):
                hits.append(node.module)
    return hits


class ArchitectureBoundaryTest(unittest.TestCase):
    def test_gui_can_import_core(self) -> None:
        import factory.gui.adapters as adapters
        import factory.gui.presentation.catalog as catalog
        import factory.gui.presentation.progress as progress
        import factory.service as service

        self.assertTrue(hasattr(adapters, "nav_tree"))
        self.assertTrue(hasattr(catalog, "ProviderRow"))
        self.assertTrue(hasattr(progress, "TRACK_STEPS"))
        self.assertTrue(hasattr(service, "FactoryService"))

    def test_core_python_does_not_import_gui(self) -> None:
        offenders: list[str] = []
        gui_root = PKG / "gui"
        for path in sorted(PKG.rglob("*.py")):
            if gui_root in path.parents or path == gui_root:
                continue
            if path.name == "cli.py":
                continue
            hits = _imports_gui(path)
            if hits:
                offenders.append(f"{path.relative_to(ROOT)}: {hits}")
        self.assertEqual(offenders, [])

    def test_agents_workflow_registry_events_do_not_import_gui(self) -> None:
        for relative in ("agents", "workflow.py", "models/registry.py", "events.py", "service.py"):
            for path in _py_files(relative):
                self.assertEqual(_imports_gui(path), [], msg=str(path))

    def test_cli_only_imports_gui_inside_studio_command(self) -> None:
        source = (PKG / "cli.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        studio = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "studio_cmd"
        )
        studio_hits = []
        for node in ast.walk(studio):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("factory.gui"):
                studio_hits.append(node.module)
        self.assertEqual(studio_hits, ["factory.gui.app"])
        outside = []
        for node in tree.body:
            if node is studio:
                continue
            for child in ast.walk(node):
                if isinstance(child, ast.ImportFrom) and child.module and child.module.startswith("factory.gui"):
                    outside.append(child.module)
                if isinstance(child, ast.Import):
                    for alias in child.names:
                        if alias.name.startswith("factory.gui"):
                            outside.append(alias.name)
        self.assertEqual(outside, [])

    def test_core_imports_when_gui_is_unimportable(self) -> None:
        script = (
            "import importlib.abc, sys\n"
            "class Block(importlib.abc.MetaPathFinder):\n"
            "    def find_spec(self, fullname, path, target=None):\n"
            "        if fullname == 'factory.gui' or fullname.startswith('factory.gui.'):\n"
            "            raise ModuleNotFoundError(fullname)\n"
            "        return None\n"
            "sys.meta_path.insert(0, Block())\n"
            + "".join(f"import {name}\n" for name in CORE_IMPORT_TARGETS)
            + "print('ok')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok", result.stdout)

    def test_core_pytest_still_passes_without_gui(self) -> None:
        script = (
            "import importlib.abc, sys\n"
            "class Block(importlib.abc.MetaPathFinder):\n"
            "    def find_spec(self, fullname, path, target=None):\n"
            "        if fullname == 'factory.gui' or fullname.startswith('factory.gui.'):\n"
            "            raise ModuleNotFoundError(fullname)\n"
            "        return None\n"
            "sys.meta_path.insert(0, Block())\n"
            "import pytest\n"
            f"raise SystemExit(pytest.main({list(CORE_PYTEST)!r}))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)


class PresentationStaysInGuiTest(unittest.TestCase):
    def test_core_has_no_screen_vocabulary_types(self) -> None:
        blob = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                PKG / "service.py",
                PKG / "events.py",
                PKG / "models" / "registry.py",
                PKG / "workflow.py",
            )
        )
        for needle in (
            "class DashboardView",
            "class InspectorView",
            "class NavNode",
            "class ProviderRow",
            "class ProfileAdvanced",
            "TRACK_STEPS",
            "Inherit Default",
            "get_xxx_page",
        ):
            self.assertNotIn(needle, blob)

    def test_events_are_generic(self) -> None:
        events = (PKG / "events.py").read_text(encoding="utf-8")
        self.assertIn("workflow_started", events)
        self.assertIn("stage_started", events)
        self.assertNotIn("token_stream", events)
        self.assertNotIn("agent_started", events)
        self.assertNotIn("Writing", events)
        self.assertNotIn("○", events)
