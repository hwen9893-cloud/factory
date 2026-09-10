"""Offline core tests. No live model HTTP.

Covers PromptManager, config, providers, JSON parsing, memory merge,
chapter workflow, revision cap, storage, and Pydantic schemas.
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from factory.memory.store import JsonMemoryStore
from factory.memory.updater import MemoryUpdater
from factory.models.client import ModelClient
from factory.models.jsonutil import parse_json_object
from factory.models.providers import MockModelProvider, MockProvider, ProviderError, build_provider
from factory.models.types import GenerationConfig, ModelProfile
from factory.prompts import REQUIRED_HEADINGS, PromptError, PromptManager, substitute
from factory.schema.models import Character, CultivationSystem, PlotThread
from factory.settings import Settings, load_settings
from factory.storage import BookRepository
from factory.workflow import SimpleWorkflow
from helpers import install_mock

FACTORY = Path(__file__).resolve().parents[1] / "factory"


# --- 1. PromptManager ---


def test_packaged_prompts_have_required_headings() -> None:
    manager = PromptManager()
    sections = manager.load_sections("chapter_writer")
    for heading in REQUIRED_HEADINGS:
        assert heading in sections
    loaded = manager.load("chapter_writer")
    assert loaded["system"]
    assert "# Output Format" in loaded["user"]


def test_render_replaces_placeholders_and_keeps_json_braces(tmp_path: Path) -> None:
    (tmp_path / "sample.md").write_text(
        "# Role\n系统\n\n# Objective\n写 {{story_title}}\n\n"
        "# Input\n{{genre}}\n\n# Requirements\nx\n\n# Constraints\ny\n\n"
        "# Output Format\n{\"ok\": true}\n",
        encoding="utf-8",
    )
    rendered = PromptManager(tmp_path).render("sample", story_title="残灵", genre="修仙")
    assert rendered["system"] == "系统"
    assert "残灵" in rendered["user"]
    assert "{{story_title}}" not in rendered["user"]
    assert '{"ok": true}' in rendered["user"]
    assert substitute('{"a": "{{title}}", "b": {"c": 1}}', {"title": "甲"}) == '{"a": "甲", "b": {"c": 1}}'


def test_missing_prompt_raises(tmp_path: Path) -> None:
    with pytest.raises(PromptError):
        PromptManager(tmp_path).load("does-not-exist")


# --- 2. config loader ---


def test_config_priority_project_then_env_then_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("FACTORY_"):
            monkeypatch.setenv(key, "")
    path = tmp_path / "factory.yaml"
    path.write_text(
        "generation:\n  chapter_target_words: 1000\n  max_revision_rounds: 4\n"
        "models:\n  writer:\n    provider: anthropic\n    model: claude-test\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FACTORY_CHAPTER_TARGET_WORDS", "2000")
    settings = load_settings(
        path,
        overrides={"generation": {"chapter_target_words": 3000}, "provider": "mock"},
    )
    assert settings.chapter_target_words == 3000
    assert settings.max_revisions == 4
    assert settings.profiles["writer"].provider == "mock"
    assert settings.profiles["writer"].model == "claude-test"


def test_default_config_uses_mock_profiles(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("FACTORY_"):
            monkeypatch.setenv(key, "")
    monkeypatch.setattr("factory.settings.discover_project_config", lambda explicit=None: explicit)
    settings = load_settings()
    assert settings.profiles["writer"].provider == "mock"
    assert "architect" in settings.profiles
    assert settings.max_revisions == 2


# --- 3. model provider abstraction ---


def test_mock_model_provider_returns_fixed_json_for_prompt() -> None:
    provider = MockModelProvider(by_prompt={"本章任务": {"title": "固定章", "scenes": []}})
    payload = provider.complete_structured(
        [{"role": "user", "content": "请根据本章任务列出场景"}],
        model="planner",
        config=GenerationConfig(),
        schema={"title": "string"},
        purpose="chapter_plan",
    )
    assert payload == {"title": "固定章", "scenes": []}


def test_mock_model_provider_purpose_overrides_default_fixture() -> None:
    provider = MockModelProvider(by_purpose={"review": {"score": 11, "must_fix": ["钩子"], "passed": False}})
    payload = provider.complete_structured(
        [{"role": "user", "content": "审稿"}],
        model="reviewer",
        config=GenerationConfig(),
        schema={},
        purpose="review",
    )
    assert payload["score"] == 11
    outline = provider.complete_structured(
        [{"role": "user", "content": "大纲"}],
        model="planner",
        config=GenerationConfig(),
        schema={},
        purpose="outline",
    )
    assert "volumes" in outline


def test_build_provider_mock_and_unknown() -> None:
    provider = build_provider(ModelProfile(name="t", provider="mock", model="x"))
    assert isinstance(provider, MockProvider)
    with pytest.raises(ProviderError):
        build_provider(ModelProfile(name="t", provider="not-a-vendor", model="x"))


def test_agents_and_workflow_do_not_import_vendor_sdks() -> None:
    banned = ("import openai", "from openai", "import anthropic", "from anthropic", "import google.genai", "from google.genai")
    for path in (FACTORY / "agents").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in banned:
            assert needle not in text, f"{path.name} imports vendor SDK"
    workflow = (FACTORY / "workflow.py").read_text(encoding="utf-8")
    for needle in banned:
        assert needle not in workflow


def test_client_uses_injected_mock_not_network(tmp_path: Path) -> None:
    settings = Settings(
        provider="mock",
        data_dir=tmp_path,
        default_book="demo",
        workflow=(),
        recent_chapters=1,
        prev_tail_chars=10,
        profiles={"planner": ModelProfile("planner", "mock", "planner")},
    )
    provider = MockModelProvider(by_prompt={"种子": {"ok": True}})
    client = ModelClient(settings)
    install_mock(client, provider)
    payload = client.generate_structured(
        [{"role": "user", "content": "故事种子：一场试炼"}],
        {"ok": "boolean"},
        profile="planner",
        purpose="custom",
    )
    assert payload == {"ok": True}
    assert provider.call_count == 1


# --- 4. JSON structured output parsing ---


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('{"a": 1}', {"a": 1}),
        ("```json\n{\"ok\": true}\n```", {"ok": True}),
        ("废话在前\n{\"k\": \"v\"}\n废话在后", {"k": "v"}),
    ],
)
def test_parse_json_object_accepts_messy_model_text(raw: str, expected: dict) -> None:
    assert parse_json_object(raw) == expected


def test_parse_json_object_rejects_non_objects() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        parse_json_object("[1, 2]")
    with pytest.raises(ValueError):
        parse_json_object("not json at all")


# --- 5. story memory merge ---


def test_memory_merge_facts_threads_and_character_state(book_root: Path, repo: BookRepository) -> None:
    store = JsonMemoryStore(repo, "demo")
    updater = MemoryUpdater(store, max_major_events=5, max_open_threads=10)
    updater.sync_from_knowledge(
        world=repo.load_world("demo"),
        characters=repo.load_characters("demo"),
        architecture={"protagonist_arc": "接剑"},
        story_seed="种子",
    )
    memory = updater.apply(
        1,
        {
            "summary": "反击",
            "events": [{"event_name": "演武场反击"}],
            "character_changes": [{"id": "knowledge.character.0001", "note": "旧伤加重", "location": "演武场"}],
            "new_facts": ["陆沉当众使出青岚剑诀"],
            "unresolved_threads": [{"id": "thread.a", "text": "执事注意他"}],
            "current_conflict": "外门资格",
        },
    )
    assert memory.entities.characters["knowledge.character.0001"].location == "演武场"
    assert "陆沉当众使出青岚剑诀" in memory.canon.facts
    memory = updater.apply(
        2,
        {
            "summary": "追查",
            "resolved_threads": [{"id": "thread.a", "text": "执事注意他"}],
            "unresolved_threads": [{"id": "thread.b", "text": "禁术代价"}],
        },
    )
    open_ids = {item.id for item in memory.plot.open_threads}
    assert "thread.a" not in open_ids
    assert "thread.b" in open_ids
    assert len(memory.plot.closed_threads) == 1


# --- 6. chapter workflow ---


def test_chapter_workflow_runs_offline(book_root: Path, settings: Settings, mock_provider: MockModelProvider) -> None:
    wf = SimpleWorkflow(settings, "demo")
    install_mock(wf.models, mock_provider)
    result = wf.run()
    chapter = book_root / "demo" / "chapters" / "ch001"
    assert (book_root / "demo" / "outline.json").exists()
    assert (chapter / "final.md").exists()
    assert (chapter / "pipeline.json").exists()
    assert result["pipeline"]["status"] == "completed"
    assert mock_provider.call_count > 0
    body = (chapter / "final.md").read_text(encoding="utf-8")
    assert "sk-" not in body


# --- 7. revision retry limit ---


def test_revision_stops_at_max_rounds(book_root: Path, settings: Settings) -> None:
    settings = replace(settings, max_revisions=2)
    mock = MockModelProvider(
        by_purpose={"review": {"score": 10, "must_fix": ["重写"], "problems": ["弱"], "passed": False, "pass": False}}
    )
    wf = SimpleWorkflow(settings, "demo")
    install_mock(wf.models, mock)
    wf.run(("world_builder", "character", "novel_architect", "outline", "volume_planner"))
    result = wf.run(("chapter_planner", "chapter_writer", "continuity", "reviewer", "revision", "memory"))
    assert result["status"] == "max_revisions"
    assert result["revision_attempts"] == 2
    assert (book_root / "demo" / "chapters" / "ch001" / "final.md").exists()


# --- 8. storage ---


def test_book_repository_chapter_and_current_book(repo: BookRepository) -> None:
    repo.save_draft("demo", 1, "第1章", "初稿正文")
    repo.save_final("demo", 1, "第1章", "定稿正文")
    repo.save_outline("demo", {"title": "残灵古剑", "volumes": []})
    repo.set_current_book("demo")
    assert repo.load_draft("demo", 1) == {"title": "第1章", "body": "初稿正文"}
    assert repo.load_final("demo", 1)["body"] == "定稿正文"
    assert repo.load_outline("demo")["title"] == "残灵古剑"
    assert repo.current_book() == "demo"
    assert repo.max_final_chapter("demo") == 1
    assert repo.load_draft("demo", 9) is None


def test_missing_book_raises(tmp_path: Path) -> None:
    repo = BookRepository(tmp_path)
    with pytest.raises(FileNotFoundError):
        repo.load_meta("ghost")


# --- 9. Pydantic schema ---


def test_character_schema_legacy_fields_and_json_roundtrip() -> None:
    card = Character.model_validate(
        {
            "id": "c1",
            "name": "陆沉",
            "age": 17,
            "realm": "炼气期",
            "sect": "青岚宗",
            "goal": "活过试炼",
            "weapons": ["木剑"],
        }
    )
    assert card.cultivation_realm == "炼气期"
    assert card.faction == "青岚宗"
    assert card.goals == ["活过试炼"]
    assert card.weapons[0].name == "木剑"
    cloned = Character.model_validate(card.model_dump(mode="json"))
    assert cloned.name == "陆沉"


def test_schema_merge_and_plot_status_alias() -> None:
    system = CultivationSystem(stages=["初期", "中期"], power_constraints=["不可越两级硬拼"])
    merged = system.merge(CultivationSystem.model_validate({"resources": [{"name": "聚气丹"}]}))
    assert merged.stages[0] == "初期"
    assert merged.resources[0].name == "聚气丹"
    thread = PlotThread.model_validate({"text": "执事追查", "status": "closed", "related_ids": ["c1"]})
    assert thread.status == "resolved"
    assert thread.involved_characters == ["c1"]
