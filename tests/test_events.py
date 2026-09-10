"""In-process workflow events and mock token streaming."""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory.cli import print_progress
from factory.events import STAGE_STARTED, TOKEN, WorkflowEvent, stage_started
from factory.gui.presentation.progress import STAGE_LABELS, status_text
from factory.models.providers import MockProvider
from factory.models.types import GenerationConfig
from factory.service import FactoryService
from factory.workflow import SimpleWorkflow
from helpers import seed_book, settings_for


class WorkflowEventTest(unittest.TestCase):
    def test_stage_started_is_domain_only(self) -> None:
        event = stage_started("chapter_writer")
        self.assertEqual(event.type, STAGE_STARTED)
        self.assertEqual(event.stage, "chapter_writer")
        self.assertEqual(event.agent, "chapter_writer")
        self.assertFalse(hasattr(event, "display"))
        self.assertEqual(status_text(event), "Writing")

    def test_cli_renderer_skips_tokens_and_maps_copy(self) -> None:
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            print_progress(WorkflowEvent(type=TOKEN, content="secret-chunk"))
            print_progress(stage_started("chapter_writer"))
        out = buf.getvalue()
        self.assertNotIn("secret-chunk", out)
        self.assertIn("→ Writing", out)
        self.assertNotIn("○", out)


class WorkflowCallbackTest(unittest.TestCase):
    def test_generate_emits_started_tokens_completed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            seed_book(tmp)
            settings = settings_for(tmp)
            SimpleWorkflow(settings, "demo").run(
                ("world_builder", "character", "novel_architect", "outline", "volume_planner")
            )
            events: list[WorkflowEvent] = []
            service = FactoryService(settings, on_progress=events.append)
            service.generate("demo", 1)
            types = [item.type for item in events]
            self.assertIn("workflow_started", types)
            self.assertIn("stage_started", types)
            self.assertIn("token", types)
            self.assertIn("stage_completed", types)
            self.assertIn("workflow_completed", types)
            self.assertTrue(any(item.agent == "chapter_writer" and item.type == "stage_started" for item in events))
            streamed = "".join(item.content for item in events if item.type == "token")
            self.assertIn("陆沉", streamed)
            self.assertGreater(len([item for item in events if item.type == "token"]), 1)
            blob = "".join(f"{item.type}{item.content}{item.message}" for item in events)
            self.assertNotIn("sk-", blob)

    def test_review_emits_reviewer_stage_completed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            seed_book(tmp)
            settings = settings_for(tmp)
            SimpleWorkflow(settings, "demo").run(
                ("world_builder", "character", "novel_architect", "outline", "volume_planner")
            )
            events: list[WorkflowEvent] = []
            service = FactoryService(settings, on_progress=events.append)
            service.plan("demo", 1)
            service.generate("demo", 1)
            service.review("demo", 1)
            self.assertTrue(
                any(
                    item.type == "stage_completed" and item.stage in {"quality_review", "reviewer"}
                    for item in events
                )
            )


class GuiProgressMappingTest(unittest.TestCase):
    def test_stage_labels_live_in_gui(self) -> None:
        self.assertEqual(STAGE_LABELS["chapter_planner"], "Planning")
        self.assertEqual(STAGE_LABELS["chapter_writer"], "Writing")
        self.assertEqual(STAGE_LABELS["continuity"], "Checking continuity")
        self.assertEqual(STAGE_LABELS["reviewer"], "Reviewing")
        self.assertEqual(STAGE_LABELS["memory"], "Updating memory")


class MockStreamTest(unittest.TestCase):
    def test_mock_stream_chunks_then_full_text(self) -> None:
        chunks: list[str] = []
        provider = MockProvider()
        result = provider.stream(
            [{"role": "user", "content": "请写陆沉"}],
            model="mock",
            config=GenerationConfig(),
            on_token=chunks.append,
        )
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(chunks), result.text)
        self.assertIn("陆沉", result.text)
