"""Versioned StoryState and atomic chapter finalization adapters."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable

from factory.schema.contracts import CharacterKnowledgeState, EntityChange, StoryState, StoryStateDelta, utc_now
from factory.storage import BookRepository


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _read(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


class StoryStateRepository:
    """Compatibility repository: hydrate old MemoryStore files, then keep versioned state."""

    def __init__(self, repo: BookRepository, book_id: str) -> None:
        self.repo = repo
        self.book_id = book_id
        self.root = repo.book_dir(book_id) / "state"
        self.current_path = self.root / "current.json"

    def load(self) -> StoryState:
        if self.current_path.exists():
            return StoryState.model_validate(_read(self.current_path, {}))
        return self._hydrate_legacy()

    def save(self, state: StoryState) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temp = self.root / ".current.json.tmp"
        temp.write_text(_dump(state.model_dump(mode="json")), encoding="utf-8")
        os.replace(temp, self.current_path)

    def snapshot(self, state: StoryState) -> Path:
        path = self.root / "snapshots" / f"v{state.state_version:06d}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(
                _dump(
                    {
                        "state_version": state.state_version,
                        "chapter_no": max(0, state.current_chapter - 1),
                        "operation_id": state.applied_operations[-1] if state.applied_operations else "",
                        "created_at": utc_now(),
                        "state": state.model_dump(mode="json"),
                    }
                ),
                encoding="utf-8",
            )
        return path

    def get_snapshot(self, version: int) -> StoryState:
        path = self.root / "snapshots" / f"v{int(version):06d}.json"
        if not path.exists():
            raise FileNotFoundError(f"StoryState snapshot not found: version {version}")
        payload = _read(path, {})
        return StoryState.model_validate(payload.get("state") or payload)

    def rollback_to(self, version: int) -> StoryState:
        state = self.get_snapshot(version)
        self.save(state)
        return state

    def _hydrate_legacy(self) -> StoryState:
        memory_root = self.repo.book_dir(self.book_id) / "memory"
        entities = _read(memory_root / "entities.json", {})
        plot = _read(memory_root / "plot.json", {})
        chars = dict(entities.get("characters") or {})
        if not chars:
            chars = {
                str(item.get("id")): dict(item)
                for item in self.repo.load_characters(self.book_id)
                if item.get("id")
            }
        return StoryState(
            current_chapter=int(self.repo.load_meta(self.book_id).get("current_chapter") or 1),
            characters=chars,
            relationships=list(entities.get("relationships") or []),
            current_conflict=str(plot.get("current_conflict") or ""),
            events=list(plot.get("major_events") or self.repo.load_timeline(self.book_id)),
            open_threads=list(plot.get("open_threads") or []),
            resolved_threads=list(plot.get("closed_threads") or []),
        )


class DeltaValidator:
    def validate(self, state: StoryState, delta: StoryStateDelta) -> None:
        if delta.operation_id in state.applied_operations:
            return
        if delta.base_state_version != state.state_version:
            raise ValueError(
                f"stale StoryStateDelta: base={delta.base_state_version}, current={state.state_version}"
            )
        if delta.chapter_no < 1:
            raise ValueError("StoryStateDelta.chapter_no must be positive")
        for change in delta.character_changes:
            if not change.id:
                raise ValueError("character change is missing id")


def apply_delta(state: StoryState, delta: StoryStateDelta) -> StoryState:
    """Pure, idempotent merge. Persistence is owned by AtomicFinalizer."""
    if delta.operation_id in state.applied_operations:
        return state.model_copy(deep=True)
    DeltaValidator().validate(state, delta)
    result = state.model_copy(deep=True)
    for change in delta.character_changes:
        current = dict(result.characters.get(change.id) or {"id": change.id})
        current.update(change.patch)
        result.characters[change.id] = current
    for rows, key in (
        (delta.cultivation_changes, "realm"),
        (delta.location_changes, "location"),
        (delta.inventory_changes, "items"),
    ):
        for raw in rows:
            cid = str(raw.get("id") or raw.get("character_id") or "")
            if cid:
                current = dict(result.characters.get(cid) or {"id": cid})
                value = raw.get(key, raw.get("value"))
                if value is not None:
                    current[key] = value
                result.characters[cid] = current
    for raw in delta.knowledge_changes:
        cid = str(raw.get("character_id") or raw.get("id") or "")
        if not cid:
            continue
        current = result.character_knowledge.get(cid, CharacterKnowledgeState(character_id=cid))
        payload = current.model_dump(mode="json")
        for key in ("known_facts", "suspected_facts", "false_beliefs", "secrets_known"):
            values = [str(item) for item in raw.get(key) or []]
            payload[key] = list(dict.fromkeys([*(payload.get(key) or []), *values]))
        payload["last_updated_chapter"] = delta.chapter_no
        result.character_knowledge[cid] = CharacterKnowledgeState.model_validate(payload)
    _append_unique(result.relationships, delta.relationship_changes)
    _append_unique(result.events, delta.timeline_events)
    _append_unique(result.open_threads, delta.new_threads)
    resolved_ids = {str(item) for item in delta.resolved_threads}
    if resolved_ids:
        moved = [item for item in result.open_threads if str(item.get("id") or item.get("text")) in resolved_ids]
        result.open_threads = [item for item in result.open_threads if item not in moved]
        _append_unique(result.resolved_threads, moved)
    for change in delta.golden_finger_changes:
        current = result.golden_fingers.get(change.id)
        payload = current.model_dump(mode="json") if current else {"golden_finger_id": change.id}
        payload.update(change.patch)
        from factory.schema.contracts import GoldenFingerState

        result.golden_fingers[change.id] = GoldenFingerState.model_validate(payload)
    if delta.main_plot_changes:
        result.current_main_plot_phase = str(delta.main_plot_changes[-1].get("phase") or result.current_main_plot_phase)
    if delta.villain_stage_changes:
        result.current_antagonist_stage = str(delta.villain_stage_changes[-1].get("stage") or result.current_antagonist_stage)
    _append_unique(result.hook_ledger, delta.hook_ledger_changes)
    _append_unique(result.payoff_ledger, delta.payoff_ledger_changes)
    result.current_chapter = max(result.current_chapter, delta.chapter_no + 1)
    result.state_version += 1
    result.applied_operations.append(delta.operation_id)
    return result


def _append_unique(target: list[Any], rows: list[Any]) -> None:
    existing = {json.dumps(item.model_dump(mode="json") if hasattr(item, "model_dump") else item, ensure_ascii=False, sort_keys=True) for item in target}
    for item in rows:
        key = json.dumps(item.model_dump(mode="json") if hasattr(item, "model_dump") else item, ensure_ascii=False, sort_keys=True)
        if key not in existing:
            target.append(item)
            existing.add(key)


class AtomicFinalizer:
    """Commit final text, record, StoryState, and legacy projections as one recoverable unit."""

    def __init__(self, repo: BookRepository, book_id: str) -> None:
        self.repo = repo
        self.book_id = book_id
        self.states = StoryStateRepository(repo, book_id)
        self._recover_prepared()

    def finalize(
        self,
        *,
        title: str,
        body: str,
        record: dict[str, Any],
        delta: StoryStateDelta,
        legacy_apply: Callable[[], None] | None = None,
        fail_after: str = "",
    ) -> StoryState:
        current = self.states.load()
        if delta.operation_id in current.applied_operations:
            return current
        next_state = apply_delta(current, delta)
        book_root = self.repo.book_dir(self.book_id)
        tx = book_root / ".transactions" / delta.operation_id
        stage = tx / "stage"
        backup = tx / "backup"
        stage.mkdir(parents=True, exist_ok=True)
        backup.mkdir(parents=True, exist_ok=True)
        chapter = self.repo.chapter_dir(self.book_id, delta.chapter_no)
        final_path = chapter / "final.md"
        record_path = chapter / "record.json"
        state_path = self.states.current_path
        targets = ((final_path, "final.md"), (record_path, "record.json"), (state_path, "state.json"))
        for target, name in targets:
            if target.exists():
                shutil.copy2(target, backup / name)
        for dirname in ("memory", "knowledge"):
            source = book_root / dirname
            if source.exists():
                shutil.copytree(source, backup / dirname, dirs_exist_ok=True)
        (stage / "final.md").write_text(f"# {title}\n\n{body.strip()}\n", encoding="utf-8")
        (stage / "record.json").write_text(_dump(record), encoding="utf-8")
        (stage / "state.json").write_text(_dump(next_state.model_dump(mode="json")), encoding="utf-8")
        (tx / "manifest.json").write_text(
            _dump(
                {
                    "operation_id": delta.operation_id,
                    "chapter_no": delta.chapter_no,
                    "state_version_after": next_state.state_version,
                    "status": "prepared",
                }
            ),
            encoding="utf-8",
        )
        try:
            for target, name in targets:
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(stage / name, target)
                if fail_after == name:
                    raise RuntimeError(f"injected transaction failure after {name}")
            if legacy_apply:
                legacy_apply()
            self.states.snapshot(next_state)
            (tx / "manifest.json").write_text(_dump({"operation_id": delta.operation_id, "status": "committed"}), encoding="utf-8")
            return next_state
        except Exception:
            self._rollback_transaction(tx, delta.chapter_no, next_state.state_version)
            raise

    def _recover_prepared(self) -> None:
        root = self.repo.book_dir(self.book_id) / ".transactions"
        if not root.exists():
            return
        for tx in root.iterdir():
            manifest_path = tx / "manifest.json"
            if not manifest_path.exists():
                continue
            manifest = _read(manifest_path, {})
            if manifest.get("status") != "prepared":
                continue
            self._rollback_transaction(
                tx,
                int(manifest.get("chapter_no") or 0),
                int(manifest.get("state_version_after") or 0),
            )

    def _rollback_transaction(self, tx: Path, chapter_no: int, state_version_after: int) -> None:
        book_root = self.repo.book_dir(self.book_id)
        backup = tx / "backup"
        chapter = self.repo.chapter_dir(self.book_id, chapter_no)
        targets = (
            (chapter / "final.md", "final.md"),
            (chapter / "record.json", "record.json"),
            (self.states.current_path, "state.json"),
        )
        for target, name in targets:
            saved = backup / name
            if saved.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(saved, target)
            elif target.exists():
                target.unlink()
        for dirname in ("memory", "knowledge"):
            target = book_root / dirname
            saved = backup / dirname
            if target.exists():
                shutil.rmtree(target)
            if saved.exists():
                shutil.copytree(saved, target)
        snapshot = self.states.root / "snapshots" / f"v{state_version_after:06d}.json"
        if state_version_after and snapshot.exists():
            snapshot.unlink()
        manifest = _read(tx / "manifest.json", {})
        manifest["status"] = "rolled_back"
        manifest["recovered"] = True
        (tx / "manifest.json").write_text(_dump(manifest), encoding="utf-8")
