from __future__ import annotations

import json

import pytest

from factory.schema.contracts import EntityChange, StoryStateDelta
from factory.state import AtomicFinalizer, StoryStateRepository, apply_delta


def _delta(version: int = 0) -> StoryStateDelta:
    return StoryStateDelta(
        operation_id="chapter.000001.test",
        chapter_no=1,
        base_state_version=version,
        character_changes=[EntityChange(id="knowledge.character.0001", patch={"location": "演武场"})],
        timeline_events=[{"id": "event.1", "text": "陆沉完成反击"}],
        new_threads=[{"id": "thread.1", "text": "执事关注陆沉"}],
    )


def test_apply_delta_is_idempotent(repo) -> None:
    state = StoryStateRepository(repo, "demo").load()
    updated = apply_delta(state, _delta(state.state_version))
    repeated = apply_delta(updated, _delta(state.state_version))
    assert updated == repeated
    assert repeated.state_version == state.state_version + 1
    assert repeated.characters["knowledge.character.0001"]["location"] == "演武场"


def test_stale_delta_is_rejected(repo) -> None:
    state = StoryStateRepository(repo, "demo").load()
    with pytest.raises(ValueError, match="stale StoryStateDelta"):
        apply_delta(state, _delta(state.state_version + 1))


def test_atomic_finalizer_commits_all_outputs(repo) -> None:
    states = StoryStateRepository(repo, "demo")
    delta = _delta(states.load().state_version)
    final = AtomicFinalizer(repo, "demo")
    updated = final.finalize(title="第一章", body="正文", record={"ch_no": 1}, delta=delta)
    chapter = repo.chapter_dir("demo", 1)
    assert (chapter / "final.md").exists()
    assert json.loads((chapter / "record.json").read_text(encoding="utf-8"))["ch_no"] == 1
    assert states.load().state_version == updated.state_version
    assert (states.root / "snapshots" / "v000001.json").exists()
    assert states.get_snapshot(1) == updated


def test_atomic_finalizer_rolls_back_partial_failure(repo) -> None:
    states = StoryStateRepository(repo, "demo")
    original = states.load()
    delta = _delta(original.state_version)
    with pytest.raises(RuntimeError, match="injected transaction failure"):
        AtomicFinalizer(repo, "demo").finalize(
            title="第一章",
            body="不应保留",
            record={"ch_no": 1},
            delta=delta,
            fail_after="record.json",
        )
    chapter = repo.chapter_dir("demo", 1)
    assert not (chapter / "final.md").exists()
    assert not (chapter / "record.json").exists()
    assert states.load() == original
    manifest = repo.book_dir("demo") / ".transactions" / delta.operation_id / "manifest.json"
    assert json.loads(manifest.read_text(encoding="utf-8"))["status"] == "rolled_back"


def test_atomic_finalizer_does_not_apply_operation_twice(repo) -> None:
    states = StoryStateRepository(repo, "demo")
    delta = _delta(states.load().state_version)
    finalizer = AtomicFinalizer(repo, "demo")
    first = finalizer.finalize(title="第一章", body="正文", record={"ch_no": 1}, delta=delta)
    second = finalizer.finalize(title="第一章", body="不同正文", record={"ch_no": 1}, delta=delta)
    assert first == second
    assert repo.load_final("demo", 1)["body"] == "正文"
