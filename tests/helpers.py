"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

from factory.models.types import ModelProfile
from factory.settings import Settings
from factory.storage import BookRepository

SEED = "灵根残缺少年在宗门试炼中被逼入绝境，借旧伤中残留的古剑灵息反击。"

CHARACTERS = [
    {
        "id": "knowledge.character.0001",
        "name": "陆沉",
        "status": "alive",
        "personality": "克制",
        "voice_style": "短句",
    },
    {
        "id": "knowledge.character.0002",
        "name": "赵衡",
        "status": "alive",
        "personality": "傲慢",
        "voice_style": "讥讽",
    },
]


FULL_WORKFLOW = (
    "world_builder",
    "character",
    "novel_architect",
    "outline",
    "volume_planner",
    "chapter_planner",
    "chapter_writer",
    "continuity",
    "reviewer",
    "revision",
    "memory",
)


def settings_for(tmp: Path) -> Settings:
    return Settings(
        provider="mock",
        data_dir=tmp,
        default_book="demo",
        workflow=FULL_WORKFLOW,
        recent_chapters=3,
        prev_tail_chars=400,
        workflows={
            "run": FULL_WORKFLOW,
            "plan": FULL_WORKFLOW[:6],
            "write": ("chapter_writer",),
            "review": ("continuity", "reviewer", "revision", "memory"),
        },
        profiles={
            "architect": ModelProfile("architect", "mock", "mock-arch", 0.3, 30),
            "planner": ModelProfile("planner", "mock", "mock-plan", 0.2, 30),
            "writer": ModelProfile("writer", "mock", "mock-write", 0.7, 30),
            "reviewer": ModelProfile("reviewer", "mock", "mock-review", 0.1, 30),
        },
    )


def install_mock(client, provider) -> None:
    """Route every ModelClient call through a test double. No live vendors."""
    client._providers.clear()
    client._provider = lambda spec: provider


def seed_book(tmp: Path, book_id: str = "demo") -> BookRepository:
    repo = BookRepository(tmp)
    repo.init_book(
        book_id,
        title="残灵古剑",
        genre="修仙爽文",
        style="克制、短句",
        story_seed=SEED,
        knowledge={
            "world": {
                "summary": "青岚宗外门",
                "realms": [{"id": "knowledge.realm.0001", "name": "炼气期"}],
                "sects": [{"id": "knowledge.sect.0001", "name": "青岚宗"}],
            },
            "characters": CHARACTERS,
            "timeline": [],
        },
    )
    return repo
