"""Preview-first, idempotent framework import over the existing BookRepository."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from factory.framework.models import ImportChange, ImportMode, ImportPreview, ParsedFramework
from factory.framework.normalizer import FrameworkNormalizer
from factory.framework.parser import FrameworkParser
from factory.framework.validator import ReferenceValidator, SchemaValidator
from factory.schema.contracts import StoryBible
from factory.schema.store import SchemaStore
from factory.storage import BookRepository


class StoryBibleRepository:
    def __init__(self, repo: BookRepository, book_id: str) -> None:
        self.repo = repo
        self.book_id = book_id
        self.root = repo.book_dir(book_id) / "framework"
        self.path = self.root / "story_bible.v2.json"
        self.imports_path = self.root / "imports.json"

    def load(self) -> StoryBible:
        if self.path.exists():
            return StoryBible.model_validate(json.loads(self.path.read_text(encoding="utf-8")))
        if not self.repo.exists(self.book_id):
            return StoryBible()
        legacy = SchemaStore(self.repo, self.book_id).load()
        meta = self.repo.load_meta(self.book_id)
        outline = self.repo.load_outline(self.book_id) or {}
        chapters = [chapter for volume in outline.get("volumes") or [] for chapter in volume.get("chapters") or []]
        return StoryBible(
            title=str(meta.get("title") or self.book_id),
            genre=str(meta.get("genre") or ""),
            premise=str(meta.get("story_seed") or ""),
            world=legacy.world,
            characters=legacy.characters,
            plot_threads=legacy.plot_threads,
            foreshadowing=legacy.foreshadowing,
            chapter_outlines=chapters,
        )

    def save(self, bible: StoryBible) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(bible.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        store = SchemaStore(self.repo, self.book_id)
        store.save_world(bible.world)
        store.save_characters(bible.characters)
        store.save_plot(bible.plot_threads, bible.foreshadowing)
        if bible.chapter_outlines:
            volumes = list(bible.volume_plans)
            if volumes and all("chapters" in item for item in volumes):
                outline_volumes = volumes
            else:
                first = volumes[0] if volumes else {}
                outline_volumes = [
                    {
                        "volume_no": int(first.get("volume_no") or 1),
                        "title": str(first.get("title") or "第一卷"),
                        "chapters": bible.chapter_outlines,
                    }
                ]
            self.repo.save_outline(self.book_id, {"title": bible.title, "volumes": outline_volumes})

    def applied(self, operation_id: str) -> bool:
        return operation_id in self._imports()

    def record(self, operation_id: str, source_hash: str, mode: ImportMode) -> None:
        rows = self._imports()
        rows[operation_id] = {"source_hash": source_hash, "mode": mode.value}
        self.root.mkdir(parents=True, exist_ok=True)
        self.imports_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _imports(self) -> dict[str, Any]:
        if not self.imports_path.exists():
            return {}
        return json.loads(self.imports_path.read_text(encoding="utf-8"))


class FrameworkImporter:
    def __init__(self, repo: BookRepository, *, parser: FrameworkParser | None = None, normalizer: FrameworkNormalizer | None = None) -> None:
        self.repo = repo
        self.parser = parser or FrameworkParser()
        self.normalizer = normalizer or FrameworkNormalizer()

    def preview(self, book_id: str, path: Path, *, mode: ImportMode = ImportMode.MERGE) -> ImportPreview:
        parsed = self.normalizer.normalize(self.parser.parse_file(path))
        issues = [*parsed.issues, *SchemaValidator().validate(parsed), *ReferenceValidator().validate(parsed.bible)]
        existing = StoryBibleRepository(self.repo, book_id).load()
        changes = _diff(existing, parsed.bible, mode)
        return ImportPreview(book_id=book_id, mode=mode, source_file=parsed.source_file, source_hash=parsed.source_hash, operation_id=parsed.operation_id, bible=parsed.bible, issues=issues, changes=changes)

    def commit(self, preview: ImportPreview) -> StoryBible:
        if not preview.valid:
            raise ValueError("framework import has validation errors")
        target = StoryBibleRepository(self.repo, preview.book_id)
        if target.applied(preview.operation_id):
            return target.load()
        if preview.mode == ImportMode.CREATE and not self.repo.exists(preview.book_id):
            self.repo.init_book(preview.book_id, title=preview.bible.title or preview.book_id, genre=preview.bible.genre, style="", story_seed=preview.bible.premise)
            self.repo.set_current_book(preview.book_id)
        elif preview.mode == ImportMode.CREATE and self.repo.exists(preview.book_id):
            raise FileExistsError(f"book already exists: {preview.book_id}")
        current = target.load()
        bible = preview.bible if preview.mode in {ImportMode.CREATE, ImportMode.REPLACE} else _merge_bible(current, preview.bible)
        target.save(bible)
        target.record(preview.operation_id, preview.source_hash, preview.mode)
        return bible


_COLLECTIONS = ("characters", "golden_fingers", "antagonist_stages", "main_plot_phases", "plot_threads", "foreshadowing", "payoff_rules", "hook_rules")


def _diff(before: StoryBible, after: StoryBible, mode: ImportMode) -> list[ImportChange]:
    changes: list[ImportChange] = []
    for name in _COLLECTIONS:
        old = {_entity_id(item): item.model_dump(mode="json") for item in getattr(before, name)}
        new = {_entity_id(item): item.model_dump(mode="json") for item in getattr(after, name)}
        for key, value in new.items():
            if key not in old:
                changes.append(ImportChange(action="add", entity_type=name, entity_id=key, after=value))
            elif _without_import_times(old[key]) != _without_import_times(value):
                locked = bool((old[key].get("provenance") or {}).get("locked"))
                changes.append(ImportChange(action="conflict" if locked else "modify", entity_type=name, entity_id=key, before=old[key], after=value, message="locked fact" if locked else ""))
            else:
                changes.append(ImportChange(action="unchanged", entity_type=name, entity_id=key))
        if mode == ImportMode.REPLACE:
            for key, value in old.items():
                if key not in new:
                    changes.append(ImportChange(action="delete_candidate", entity_type=name, entity_id=key, before=value))
    return changes


def _merge_bible(base: StoryBible, incoming: StoryBible) -> StoryBible:
    data = base.model_dump(mode="json")
    new = incoming.model_dump(mode="json")
    for scalar in ("title", "genre", "premise"):
        if new.get(scalar):
            data[scalar] = new[scalar]
    if new.get("world"):
        data["world"] = {**data.get("world", {}), **new["world"]}
    for name in _COLLECTIONS:
        merged = {_entity_id_raw(item): item for item in data.get(name) or []}
        for item in new.get(name) or []:
            key = _entity_id_raw(item)
            current = merged.get(key)
            if current and bool((current.get("provenance") or {}).get("locked")):
                continue
            merged[key] = {**(current or {}), **item}
        data[name] = list(merged.values())
    for name in ("volume_plans", "chapter_outlines", "forbidden_rules"):
        if new.get(name):
            data[name] = new[name]
    if new.get("style_guide"):
        data["style_guide"] = {**data.get("style_guide", {}), **new["style_guide"]}
    return StoryBible.model_validate(data)


def _entity_id(item: Any) -> str:
    return str(getattr(item, "id", "") or getattr(item, "clue", ""))


def _entity_id_raw(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("clue") or "")


def _without_import_times(item: dict[str, Any]) -> dict[str, Any]:
    clean = json.loads(json.dumps(item))
    provenance = clean.get("provenance") or {}
    for key in ("imported_at", "created_at", "updated_at", "import_operation_id"):
        provenance.pop(key, None)
    return clean
