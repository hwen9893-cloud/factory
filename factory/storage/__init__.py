"""Book file layout. All persistent story data goes under data/books/{book_id}/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class BookRepository:
    """Read and write one book's metadata, knowledge, outline, chapters, and memory."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def book_dir(self, book_id: str) -> Path:
        return self.root / book_id

    def exists(self, book_id: str) -> bool:
        return (self.book_dir(book_id) / "meta.json").exists()

    def init_book(
        self,
        book_id: str,
        *,
        title: str,
        genre: str,
        style: str,
        story_seed: str,
        knowledge: dict[str, Any] | None = None,
    ) -> None:
        base = self.book_dir(book_id)
        if self.exists(book_id):
            raise FileExistsError(f"book already exists: {book_id}")
        knowledge = knowledge or {"world": {}, "characters": [], "timeline": []}
        _write_json(
            base / "meta.json",
            {
                "book_id": book_id,
                "title": title,
                "genre": genre,
                "style": style,
                "story_seed": story_seed,
                "current_volume": 1,
                "current_chapter": 1,
                "target_chapters": 3,
            },
        )
        _write_json(base / "knowledge" / "world.json", knowledge.get("world") or {})
        _write_json(base / "knowledge" / "characters.json", knowledge.get("characters") or [])
        _write_json(base / "knowledge" / "timeline.json", knowledge.get("timeline") or [])
        _write_json(base / "knowledge" / "plot.json", knowledge.get("plot") or {"plot_threads": [], "foreshadowing": []})
        (base / "memory").mkdir(parents=True, exist_ok=True)
        (base / "chapters").mkdir(parents=True, exist_ok=True)
        notes = base / "memory" / "notes.json"
        if not notes.exists():
            _write_json(notes, {"facts": []})

    def load_meta(self, book_id: str) -> dict[str, Any]:
        path = self.book_dir(book_id) / "meta.json"
        if not path.exists():
            raise FileNotFoundError(f"book not found: {book_id}")
        return _read_json(path, {})

    def save_meta(self, book_id: str, meta: dict[str, Any]) -> None:
        _write_json(self.book_dir(book_id) / "meta.json", meta)

    def load_world(self, book_id: str) -> dict[str, Any]:
        return _read_json(self.book_dir(book_id) / "knowledge" / "world.json", {})

    def save_world(self, book_id: str, world: dict[str, Any]) -> None:
        _write_json(self.book_dir(book_id) / "knowledge" / "world.json", world)

    def save_characters(self, book_id: str, characters: list[dict[str, Any]]) -> None:
        _write_json(self.book_dir(book_id) / "knowledge" / "characters.json", characters)

    def load_plot(self, book_id: str) -> dict[str, Any]:
        data = _read_json(self.book_dir(book_id) / "knowledge" / "plot.json", {"plot_threads": [], "foreshadowing": []})
        if not isinstance(data, dict):
            return {"plot_threads": [], "foreshadowing": []}
        data.setdefault("plot_threads", [])
        data.setdefault("foreshadowing", [])
        return data

    def save_plot(self, book_id: str, payload: dict[str, Any]) -> None:
        _write_json(self.book_dir(book_id) / "knowledge" / "plot.json", payload)

    def save_timeline(self, book_id: str, timeline: list[dict[str, Any]]) -> None:
        _write_json(self.book_dir(book_id) / "knowledge" / "timeline.json", timeline)

    def load_architecture(self, book_id: str) -> dict[str, Any] | None:
        data = _read_json(self.book_dir(book_id) / "architecture.json", None)
        return data if isinstance(data, dict) else None

    def save_architecture(self, book_id: str, architecture: dict[str, Any]) -> None:
        _write_json(self.book_dir(book_id) / "architecture.json", architecture)

    def load_volume_plan(self, book_id: str, volume_no: int) -> dict[str, Any] | None:
        data = _read_json(self.book_dir(book_id) / "volumes" / f"v{volume_no:03d}" / "plan.json", None)
        return data if isinstance(data, dict) else None

    def save_volume_plan(self, book_id: str, volume_no: int, plan: dict[str, Any]) -> None:
        _write_json(self.book_dir(book_id) / "volumes" / f"v{volume_no:03d}" / "plan.json", plan)

    def save_continuity(self, book_id: str, ch_no: int, report: dict[str, Any]) -> None:
        _write_json(self.chapter_dir(book_id, ch_no) / "continuity.json", report)

    def load_continuity(self, book_id: str, ch_no: int) -> dict[str, Any] | None:
        data = _read_json(self.chapter_dir(book_id, ch_no) / "continuity.json", None)
        return data if isinstance(data, dict) else None

    def load_character_state(self, book_id: str) -> list[dict[str, Any]]:
        data = _read_json(self.book_dir(book_id) / "memory" / "character_state.json", [])
        return data if isinstance(data, list) else []

    def save_character_state(self, book_id: str, states: list[dict[str, Any]]) -> None:
        _write_json(self.book_dir(book_id) / "memory" / "character_state.json", states)

    def load_characters(self, book_id: str) -> list[dict[str, Any]]:
        data = _read_json(self.book_dir(book_id) / "knowledge" / "characters.json", [])
        return data if isinstance(data, list) else []

    def load_timeline(self, book_id: str) -> list[dict[str, Any]]:
        data = _read_json(self.book_dir(book_id) / "knowledge" / "timeline.json", [])
        return data if isinstance(data, list) else []

    def load_outline(self, book_id: str) -> dict[str, Any] | None:
        data = _read_json(self.book_dir(book_id) / "outline.json", None)
        return data if isinstance(data, dict) else None

    def save_outline(self, book_id: str, outline: dict[str, Any]) -> None:
        _write_json(self.book_dir(book_id) / "outline.json", outline)

    def chapter_dir(self, book_id: str, ch_no: int) -> Path:
        return self.book_dir(book_id) / "chapters" / f"ch{ch_no:03d}"

    def save_chapter_plan(self, book_id: str, ch_no: int, plan: dict[str, Any]) -> None:
        _write_json(self.chapter_dir(book_id, ch_no) / "plan.json", plan)

    def load_chapter_plan(self, book_id: str, ch_no: int) -> dict[str, Any] | None:
        data = _read_json(self.chapter_dir(book_id, ch_no) / "plan.json", None)
        return data if isinstance(data, dict) else None

    def save_draft(self, book_id: str, ch_no: int, title: str, body: str) -> None:
        path = self.chapter_dir(book_id, ch_no) / "draft.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {title}\n\n{body.strip()}\n", encoding="utf-8")

    def load_draft(self, book_id: str, ch_no: int) -> dict[str, str] | None:
        path = self.chapter_dir(book_id, ch_no) / "draft.md"
        if not path.exists():
            return None
        return _split_markdown_chapter(path.read_text(encoding="utf-8"))

    def save_review(self, book_id: str, ch_no: int, review: dict[str, Any]) -> None:
        _write_json(self.chapter_dir(book_id, ch_no) / "review.json", review)

    def load_review(self, book_id: str, ch_no: int) -> dict[str, Any] | None:
        data = _read_json(self.chapter_dir(book_id, ch_no) / "review.json", None)
        return data if isinstance(data, dict) else None

    def save_final(self, book_id: str, ch_no: int, title: str, body: str) -> None:
        path = self.chapter_dir(book_id, ch_no) / "final.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {title}\n\n{body.strip()}\n", encoding="utf-8")

    def load_final(self, book_id: str, ch_no: int) -> dict[str, str] | None:
        path = self.chapter_dir(book_id, ch_no) / "final.md"
        if not path.exists():
            return None
        return _split_markdown_chapter(path.read_text(encoding="utf-8"))

    def load_recent_finals(self, book_id: str, current_ch: int, limit: int) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for ch_no in range(max(1, current_ch - limit), current_ch):
            chapter = self.load_final(book_id, ch_no) or self.load_draft(book_id, ch_no)
            if not chapter:
                continue
            items.append({"ch_no": ch_no, **chapter})
        return items

    def append_summary(self, book_id: str, ch_no: int, summary: str) -> None:
        path = self.book_dir(book_id) / "memory" / "summaries.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = json.dumps({"ch_no": ch_no, "summary": summary}, ensure_ascii=False)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(record + "\n")

    def load_summaries(self, book_id: str) -> list[dict[str, Any]]:
        path = self.book_dir(book_id) / "memory" / "summaries.jsonl"
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def load_notes(self, book_id: str) -> dict[str, Any]:
        return _read_json(self.book_dir(book_id) / "memory" / "notes.json", {"facts": []})

    def save_notes(self, book_id: str, notes: dict[str, Any]) -> None:
        _write_json(self.book_dir(book_id) / "memory" / "notes.json", notes)

    def save_pipeline_state(self, book_id: str, ch_no: int, payload: dict[str, Any]) -> None:
        _write_json(self.chapter_dir(book_id, ch_no) / "pipeline.json", payload)

    def load_pipeline_state(self, book_id: str, ch_no: int) -> dict[str, Any] | None:
        data = _read_json(self.chapter_dir(book_id, ch_no) / "pipeline.json", None)
        return data if isinstance(data, dict) else None

    def save_chapter_record(self, book_id: str, ch_no: int, payload: dict[str, Any]) -> None:
        _write_json(self.chapter_dir(book_id, ch_no) / "record.json", payload)

    def load_chapter_record(self, book_id: str, ch_no: int) -> dict[str, Any] | None:
        data = _read_json(self.chapter_dir(book_id, ch_no) / "record.json", None)
        return data if isinstance(data, dict) else None

    def list_books(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(
            path.name
            for path in self.root.iterdir()
            if path.is_dir() and (path / "meta.json").exists()
        )

    def current_book(self) -> str | None:
        path = self.root / ".current"
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8").strip()
        return text or None

    def set_current_book(self, book_id: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / ".current").write_text(book_id.strip() + "\n", encoding="utf-8")

    def max_final_chapter(self, book_id: str) -> int:
        chapters = self.book_dir(book_id) / "chapters"
        best = 0
        if not chapters.exists():
            return 0
        for path in chapters.iterdir():
            if path.is_dir() and path.name.startswith("ch") and (path / "final.md").exists():
                try:
                    best = max(best, int(path.name[2:]))
                except ValueError:
                    continue
        return best


def _split_markdown_chapter(text: str) -> dict[str, str]:
    lines = text.strip().splitlines()
    if lines and lines[0].startswith("# "):
        return {"title": lines[0][2:].strip(), "body": "\n".join(lines[1:]).strip()}
    return {"title": "", "body": text.strip()}
