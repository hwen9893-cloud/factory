"""Offline end-to-end demo. Always uses mock; never calls live model APIs."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from factory.service import FactoryService
from factory.settings import load_settings

BOOK_ID = "demo"
TITLE = "残灵古剑"
GENRE = "修仙爽文"
STYLE = "克制、短句、先抑后扬"
SEED = "灵根残缺少年在宗门试炼中被逼入绝境，借旧伤中残留的古剑灵息反击。"

REQUIRED = (
    "architecture.json",
    "outline.json",
    "volumes/v001/plan.json",
    "knowledge/world.json",
    "knowledge/characters.json",
    "chapters/ch001/plan.json",
    "chapters/ch001/draft.md",
    "chapters/ch001/final.md",
    "chapters/ch001/pipeline.json",
    "memory/canon.json",
    "memory/chapters.jsonl",
)


@dataclass(frozen=True)
class DemoReport:
    ok: bool
    book_dir: Path
    title: str
    chapter_path: Path
    body_preview: str
    pipeline_status: str
    missing: tuple[str, ...]
    result: dict[str, Any]


def run_offline_demo(data_dir: Path) -> DemoReport:
    """Init a book and run the full mock workflow under data_dir."""
    data_dir.mkdir(parents=True, exist_ok=True)
    settings = replace(load_settings(overrides={"provider": "mock"}), data_dir=data_dir)
    service = FactoryService(settings)
    book_dir = service.repo.book_dir(BOOK_ID)
    if book_dir.exists():
        shutil.rmtree(book_dir)
    service.init_book(BOOK_ID, title=TITLE, genre=GENRE, style=STYLE, seed=SEED)
    service.architect(BOOK_ID)
    result = service.continue_next(BOOK_ID)
    missing = tuple(rel for rel in REQUIRED if not (book_dir / rel).exists())
    chapter = book_dir / "chapters" / "ch001" / "final.md"
    body = chapter.read_text(encoding="utf-8") if chapter.exists() else ""
    status = str((result.get("pipeline") or {}).get("status") or result.get("status") or "")
    return DemoReport(
        ok=not missing and bool(body.strip()) and status in {"completed", "passed", "revised", "max_revisions"},
        book_dir=book_dir,
        title=str(result.get("title") or TITLE),
        chapter_path=chapter,
        body_preview=body.strip()[:240],
        pipeline_status=status,
        missing=missing,
        result=result,
    )
