"""FactoryService is the GUI/CLI façade for Chapter Studio."""

from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

from factory.events import ProgressEvent
from factory.service import FactoryService
from factory.workflow import SimpleWorkflow
from helpers import seed_book, settings_for


class ServiceContractTest(unittest.TestCase):
    def test_service_does_not_import_gui_or_vendor_sdks(self) -> None:
        import factory.service as svc

        source = inspect.getsource(svc)
        self.assertNotIn("factory.gui", source)
        self.assertNotIn("nicegui", source)
        self.assertNotIn("openai", source)
        self.assertNotIn("anthropic", source)
        self.assertNotIn("google.genai", source)
        self.assertNotIn("sqlite3", source)
        self.assertNotIn("SELECT ", source)

    def test_core_does_not_carry_gui_widgets(self) -> None:
        root = Path(__file__).resolve().parents[1] / "factory"
        events = (root / "events.py").read_text(encoding="utf-8")
        service = (root / "service.py").read_text(encoding="utf-8")
        registry = (root / "models" / "registry.py").read_text(encoding="utf-8")
        self.assertNotIn("TRACK_STEPS", events)
        self.assertNotIn("track_key", events)
        self.assertNotIn("agent_started", events)
        self.assertNotIn("token_stream", events)
        self.assertNotIn("review_completed", events)
        self.assertNotIn("Planning", events)
        self.assertNotIn("Writing", events)
        self.assertNotIn("○", events)
        self.assertNotIn("●", events)
        self.assertNotIn("✓", events)
        self.assertNotIn("class ChapterView", service)
        self.assertNotIn("class ProviderRow", service)
        self.assertNotIn("class DashboardView", service)
        self.assertNotIn("class InspectorView", service)
        self.assertNotIn("class NavNode", service)
        self.assertNotIn("class ProfileAdvanced", service)
        self.assertNotIn("label=provider_label", service)
        self.assertNotIn("DashboardSnapshot", service)
        self.assertNotIn("catalog_options", service)
        self.assertNotIn("ModelBoard", service)
        self.assertNotIn("ROLE_LABELS", registry)
        self.assertNotIn("catalog_options", registry)
        self.assertNotIn("option_label", registry)
        self.assertNotIn("def label(", registry)
        self.assertNotIn("def agent_role(", registry)
        self.assertNotIn("role_profile_name", registry)
        self.assertNotIn("Inherit Default", registry)
        self.assertNotIn("def navigator", service)
        self.assertNotIn("def inspector", service)
        self.assertNotIn("version_label", service)
        self.assertNotIn("MEMORY_PREVIEW", service)


class PresentationPurityTest(unittest.TestCase):
    def test_presentation_does_not_run_core(self) -> None:
        root = Path(__file__).resolve().parents[1] / "factory" / "gui" / "presentation"
        blob = "".join(path.read_text(encoding="utf-8") for path in sorted(root.glob("*.py")))
        self.assertNotIn("nicegui", blob)
        self.assertNotIn("SimpleWorkflow", blob)
        self.assertNotIn("BookRepository", blob)
        self.assertNotIn("SchemaStore", blob)
        self.assertNotIn("ModelClient", blob)
        self.assertIn("Inherit Default", blob)
        self.assertIn("build_model_options", blob)
        self.assertIn("ProviderRow", blob)
        self.assertIn("DashboardView", blob)

    def test_build_model_options_filters_catalog_roles(self) -> None:
        from factory.gui.presentation.model_options import INHERIT_LABEL, build_model_options, build_role_options
        from factory.models.registry import ModelRegistry, ProviderInfo
        from factory.models.types import ModelProfile

        registry = ModelRegistry(
            profiles={
                "qwen_writer": ModelProfile(
                    "qwen_writer", "qwen", "qwen-plus", display_name="Qwen Writer", roles=("writer",)
                ),
                "planner": ModelProfile("planner", "qwen", "qwen-plus", display_name="Planner", roles=("planner",)),
            },
            providers={"qwen": ProviderInfo("qwen", True)},
            agent_models={"chapter_writer": "qwen_writer"},
            default_model="qwen_writer",
        )
        opts = build_model_options(registry, agent="chapter_writer")
        self.assertEqual(opts["qwen_writer"], "Qwen Writer")
        self.assertNotIn("planner", opts)
        role_opts = build_role_options(registry, "writer")
        self.assertTrue(any(label.startswith(INHERIT_LABEL) for label in role_opts.values()))

    def test_provider_row_maps_display_outside_core(self) -> None:
        from factory.gui.presentation.catalog import build_provider_row
        from factory.service import ProviderStatus

        row = build_provider_row(
            ProviderStatus(name="anthropic", configured=False, env_names=("ANTHROPIC_API_KEY",), enabled=True)
        )
        self.assertEqual(row.display_name, "Anthropic")
        self.assertEqual(row.state, "Missing")
        self.assertEqual(row.env_hint, "ANTHROPIC_API_KEY")


class ChapterStudioServiceTest(unittest.TestCase):
    def test_navigator_and_new_chapter(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            repo = seed_book(tmp)
            repo.save_outline(
                "demo",
                {
                    "title": "残灵古剑",
                    "volumes": [
                        {
                            "volume_no": 1,
                            "title": "外门风起",
                            "chapters": [
                                {"ch_no": 1, "title": "第1章 灵根初鸣"},
                                {"ch_no": 2, "title": "第2章 剑息余波"},
                                {"ch_no": 3, "title": "第3章 试炼加码"},
                            ],
                        }
                    ],
                },
            )
            service = FactoryService(settings_for(tmp))
            self.assertEqual(service.resolve_book("demo"), "demo")
            from factory.gui.adapters import nav_tree

            tree = nav_tree(service, "demo")
            self.assertEqual(tree.label, "残灵古剑")
            self.assertEqual(tree.children[0].label, "Volume 1  外门风起")
            labels = [node.label for node in tree.children[0].children]
            self.assertEqual(labels[0], "Chapter 1  灵根初鸣")
            self.assertEqual(tree.children[0].children[0].status, "outlined")
            ch_no = service.add_chapter("demo", volume_no=1)
            self.assertEqual(ch_no, 4)
            tree = nav_tree(service, "demo")
            self.assertEqual(tree.children[0].children[-1].label, "Chapter 4")
            self.assertEqual(tree.children[0].children[-1].status, "draft")
            self.assertEqual(service.chapter_statuses("demo")[1], "outlined")

    def test_save_and_writer_context(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            seed_book(tmp)
            service = FactoryService(settings_for(tmp))
            view = service.save_chapter("demo", 1, "第1章", "剑息一闪。")
            self.assertEqual(view.word_count, len("剑息一闪。"))
            self.assertEqual(view.source, "draft")
            ctx = service.writer_context("demo", 1)
            self.assertIn("characters", ctx)
            self.assertIn("plot", ctx)
            self.assertIn("world", ctx)
            self.assertIn("recent_context", ctx)

    def test_plan_generate_review_accept(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            seed_book(tmp)
            settings = settings_for(tmp)
            SimpleWorkflow(settings, "demo").run(
                ("world_builder", "character", "novel_architect", "outline", "volume_planner")
            )
            events: list[ProgressEvent] = []
            service = FactoryService(settings, on_progress=events.append)
            assigned = service.registry.assigned_model_name("chapter_writer", default="writer")
            self.assertTrue(any(item.name == assigned for item in service.registry.list_models(enabled_only=False)))

            service.plan("demo", 1)
            self.assertTrue(service.repo.load_chapter_plan("demo", 1))
            self.assertTrue(
                any(item.stage == "chapter_planner" and item.type == "stage_started" for item in events)
            )

            service.generate("demo", 1)
            draft = service.repo.load_draft("demo", 1)
            self.assertIsNotNone(draft)
            self.assertTrue((draft or {}).get("body"))
            self.assertTrue(
                any(item.stage == "chapter_writer" and item.type == "stage_started" for item in events)
            )
            self.assertTrue(any(item.type == "token" for item in events))
            self.assertTrue(any(item.type == "workflow_completed" for item in events))

            service.review("demo", 1)
            detail = service.outline_detail("demo", ch_no=1)
            self.assertIsNotNone(detail.get("review"))
            self.assertIn("score", detail.get("review") or {})
            self.assertIn("must_fix", detail.get("review") or {})
            self.assertIsNotNone(detail.get("continuity"))
            self.assertIn("character_conflicts", detail.get("continuity") or {})
            self.assertTrue(
                any(item.stage in {"continuity_check", "continuity"} and item.type == "stage_started" for item in events)
            )
            self.assertTrue(
                any(item.stage in {"quality_review", "reviewer"} and item.type == "stage_started" for item in events)
            )

            accepted = service.accept("demo", 1, title=draft["title"], body=draft["body"])
            self.assertTrue(accepted.get("accepted"))
            self.assertTrue(service.repo.load_final("demo", 1))
            memory = service.memory_view("demo", 1)
            self.assertTrue(memory.get("applied") or memory.get("summary") is not None)
            self.assertTrue(
                any(item.stage in {"memory_update", "memory"} and item.type == "stage_started" for item in events)
            )

    def test_memory_preview_before_accept(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            seed_book(tmp)
            service = FactoryService(settings_for(tmp))
            memory = service.memory_view("demo", 1)
            self.assertFalse(memory["applied"])


class ApplicationServiceTest(unittest.TestCase):
    def test_cli_and_gui_share_chapter_entrypoints(self) -> None:
        root = Path(__file__).resolve().parents[1]
        cli = (root / "factory" / "cli.py").read_text(encoding="utf-8")
        gui = (root / "factory" / "gui" / "studio.py").read_text(encoding="utf-8")
        self.assertIn("FactoryService", cli)
        self.assertIn("service.generate", cli)
        self.assertIn("service.plan", cli)
        self.assertIn("service.review", cli)
        self.assertIn("service.revise", cli)
        self.assertIn("produce_chapter", cli)
        self.assertNotIn("SimpleWorkflow", cli)
        self.assertNotIn("BookRepository", cli)
        self.assertNotIn("SchemaStore", cli)
        self.assertIn("self.service.generate", gui)
        self.assertIn("self.service.plan", gui)
        self.assertIn("self.service.review", gui)
        self.assertIn("self.service.revise", gui)
        self.assertNotIn("SimpleWorkflow", gui)

    def test_architect_and_produce_chapter(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            seed_book(tmp)
            service = FactoryService(settings_for(tmp))
            service.architect("demo")
            status = service.book_status("demo")
            self.assertTrue(status.has_outline)
            self.assertEqual(status.next_chapter, 1)
            result = service.produce_chapter("demo", 1)
            self.assertTrue(service.repo.load_final("demo", 1))
            self.assertTrue((result.get("pipeline") or {}).get("status"))
            status = service.book_status("demo")
            self.assertEqual(status.next_chapter, 2)
            nxt = service.continue_next("demo")
            self.assertFalse(nxt.get("done"))
            self.assertTrue(service.repo.load_final("demo", 2))


class ModelAssignmentTest(unittest.TestCase):
    def test_board_default_and_role_override(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            service = FactoryService(settings_for(tmp))
            service.set_default_model("writer")
            self.assertEqual(service.settings.default_model, "writer")
            self.assertEqual(service.registry.assigned_model_name("chapter_writer", default="writer"), "writer")
            self.assertFalse(service.registry.is_override("chapter_writer"))
            self.assertEqual(service.registry.resolve_agent_model("chapter_writer").provider, "mock")
            service.set_role_model("reviewer", "reviewer")
            self.assertTrue(service.registry.is_override("reviewer"))
            self.assertEqual(service.registry.assigned_model_name("continuity"), "reviewer")
            spec = service.registry.get_model("writer")
            self.assertEqual(spec.provider, "mock")
            self.assertEqual(spec.model, "mock-write")
            self.assertTrue(hasattr(spec, "base_url"))
            self.assertTrue(hasattr(spec, "api_key_env"))

    def test_persist_writes_profile_ids_only(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            path = tmp / "local.yaml"
            from factory.settings import save_model_assignments

            save_model_assignments(
                default_model="qwen_writer",
                overrides={"world_builder": "claude_architect", "reviewer": "gpt_reviewer"},
                path=path,
            )
            text = path.read_text(encoding="utf-8")
            self.assertIn("qwen_writer", text)
            self.assertIn("claude_architect", text)
            self.assertIn("gpt_reviewer", text)
            self.assertNotIn("base_url", text)
            self.assertNotIn("compatible-mode", text)
            self.assertNotIn("openai.OpenAI", text)
            self.assertNotIn("API_KEY", text)
            self.assertNotIn("sk-", text)

    def test_gui_stores_profile_ids_not_vendor_branches(self) -> None:
        root = Path(__file__).resolve().parents[1] / "factory" / "gui"
        blob = "".join(path.read_text(encoding="utf-8") for path in sorted(root.rglob("*.py")))
        self.assertIn("Writer Model", blob)
        self.assertIn("set_role_model", blob)
        self.assertIn("profile_id", blob)
        self.assertIn("provider_statuses", blob)
        self.assertIn("test_connection", blob)
        self.assertNotIn('== "Qwen"', blob)
        self.assertNotIn("call_qwen", blob)
        self.assertNotIn("OpenAI(", blob)
        self.assertNotIn("Anthropic(", blob)
        self.assertIn("○", blob)
        self.assertIn("TRACK_STEPS", blob)
        self.assertIn("STAGE_LABELS", blob)
        self.assertIn("status_text", blob)
        self.assertNotIn("kafka", blob.lower())
        self.assertNotIn("celery", blob.lower())
        self.assertNotIn("dotenv.set_key", blob)
        self.assertNotIn('open(".env"', blob)
        self.assertNotIn("open('.env'", blob)
        self.assertNotIn("password=True", blob)
        self.assertIn("build_dashboard", blob)
        self.assertIn('"/studio"', blob)
        self.assertIn('"/bible"', blob)
        self.assertIn('"/outline"', blob)
        self.assertIn('"/memory"', blob)
        self.assertIn('"/settings"', blob)
        self.assertIn("story_bible", blob)
        self.assertIn("memory_overview", blob)
        self.assertIn("continue_next", blob)
        self.assertNotIn("SimpleWorkflow", blob)
        self.assertNotIn("BookRepository", blob)
        self.assertNotIn("SchemaStore", blob)


class GuiPagesServiceTest(unittest.TestCase):
    def test_dashboard_bible_outline_memory_settings(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            repo = seed_book(tmp)
            repo.save_plot(
                "demo",
                {
                    "plot_threads": [{"id": "t1", "title": "执事注意到不该出现的剑息", "status": "open"}],
                    "foreshadowing": [{"id": "f1", "clue": "旧伤中的古剑灵息", "resolved": False}],
                },
            )
            repo.save_final("demo", 1, "第1章 灵根初鸣", "陆沉站在演武场。")
            from factory.models.usage import UsageRecord, UsageStore, now_timestamp

            UsageStore.for_data_dir(tmp).record(
                UsageRecord(
                    timestamp=now_timestamp(),
                    agent="chapter_writer",
                    provider="mock",
                    model="mock-write",
                    input_tokens=1,
                    output_tokens=1,
                    total_tokens=2,
                    latency=1.0,
                    success=True,
                    retry_count=0,
                    estimated_cost=None,
                    book_id="demo",
                )
            )
            service = FactoryService(settings_for(tmp))
            status = service.book_status("demo")
            self.assertEqual(status.title, "残灵古剑")
            chapter = service.load_chapter("demo", 1)
            self.assertGreaterEqual(chapter.word_count, len("陆沉站在演武场。"))
            plot = service.list_plot("demo")
            self.assertTrue(
                any(item.get("title") == "执事注意到不该出现的剑息" for item in plot.get("threads") or [])
            )
            usage = service.recent_usage(book_id="demo")
            self.assertTrue(any(item.agent == "chapter_writer" for item in usage))

            bible = service.story_bible("demo")
            self.assertIn("青岚宗", (bible.get("world") or {}).get("summary", ""))
            self.assertTrue(any(item.get("name") == "陆沉" for item in bible.get("characters") or []))
            world = service.save_world_bible("demo", summary="青岚宗外门（改）", rules=["不得自造境界"])
            self.assertEqual(world["summary"], "青岚宗外门（改）")
            self.assertIn("不得自造境界", world["rules"])
            character = service.save_character_bible("demo", "knowledge.character.0001", {"personality": "更克制"})
            self.assertEqual(character["personality"], "更克制")

            detail = service.outline_detail("demo")
            self.assertEqual(detail["kind"], "book")
            layers = service.memory_overview("demo")
            self.assertIn("canon", layers)
            self.assertTrue(
                any(item.get("clue") == "旧伤中的古剑灵息" for item in (service.list_plot("demo").get("foreshadowing") or []))
            )

            overlay = tmp / "overlay.yaml"
            runtime = service.save_runtime(
                chapter_target_words=1200,
                max_revision_rounds=1,
                recent_chapters=2,
                persist=True,
                path=overlay,
            )
            self.assertEqual(runtime.chapter_target_words, 1200)
            self.assertEqual(runtime.max_revision_rounds, 1)
            text = overlay.read_text(encoding="utf-8")
            self.assertIn("1200", text)
            self.assertNotIn("sk-", text)
            self.assertNotIn("API_KEY", text)
            self.assertNotIn("DASHSCOPE", text)


class ApiSettingsTest(unittest.TestCase):
    def test_statuses_never_include_secret_values(self) -> None:
        import json
        import os
        from unittest.mock import patch

        secret = "sk-secret-TESTVALUE-xyz"
        with tempfile.TemporaryDirectory() as raw:
            service = FactoryService(settings_for(Path(raw)))
            with patch.dict(
                os.environ,
                {
                    "OPENAI_API_KEY": secret,
                    "ANTHROPIC_API_KEY": "",
                    "GEMINI_API_KEY": "",
                    "GOOGLE_API_KEY": "",
                    "DASHSCOPE_API_KEY": "",
                    "QWEN_API_KEY": "",
                    "OPENROUTER_API_KEY": "",
                },
                clear=False,
            ):
                rows = service.provider_statuses()
        names = [row.name for row in rows]
        self.assertIn("qwen", names)
        self.assertIn("openai", names)
        self.assertIn("anthropic", names)
        self.assertIn("gemini", names)
        self.assertIn("openrouter", names)
        blob = json.dumps([row.__dict__ for row in rows])
        self.assertNotIn(secret, blob)
        openai = next(row for row in rows if row.name == "openai")
        self.assertTrue(openai.configured)
        self.assertEqual(openai.env_names, ("OPENAI_API_KEY",))
        claude = next(row for row in rows if row.name == "anthropic")
        self.assertFalse(claude.configured)
        self.assertFalse(hasattr(claude, "label"))

    def test_connection_missing_key_names_env_not_secret(self) -> None:
        import os
        from unittest.mock import patch

        from factory.models.client import ModelClient

        with tempfile.TemporaryDirectory() as raw:
            service = FactoryService(settings_for(Path(raw)))
            with patch.dict(
                os.environ,
                {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": "sk-should-not-appear"},
                clear=False,
            ):
                with patch.object(ModelClient, "generate", return_value="pong") as gen:
                    result = service.test_connection("anthropic")
        self.assertFalse(result.ok)
        self.assertIn("ANTHROPIC_API_KEY", result.message)
        self.assertNotIn("sk-should-not-appear", result.message)
        gen.assert_not_called()

    def test_connection_mock_ok_offline(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            service = FactoryService(settings_for(Path(raw)))
            result = service.test_connection("mock")
        self.assertTrue(result.ok)
        self.assertEqual(result.message, "ok")

    def test_connection_unknown_provider(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            service = FactoryService(settings_for(Path(raw)))
            result = service.test_connection("not-a-vendor")
        self.assertFalse(result.ok)
        self.assertIn("unknown", result.message)

    def test_qwen_fallback_configured_without_primary(self) -> None:
        import os
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as raw:
            service = FactoryService(settings_for(Path(raw)))
            with patch.dict(
                os.environ,
                {"DASHSCOPE_API_KEY": "", "QWEN_API_KEY": "sk-qwen-fallback-secret"},
                clear=False,
            ):
                qwen = next(row for row in service.provider_statuses() if row.name == "qwen")
        self.assertTrue(qwen.configured)
        self.assertIn("DASHSCOPE_API_KEY", qwen.env_names)
        self.assertIn("QWEN_API_KEY", qwen.env_names)
        self.assertNotIn("sk-qwen-fallback-secret", qwen.env_names)
