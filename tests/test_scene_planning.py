from __future__ import annotations

from factory.pipeline.chapter import expand_stages
from factory.pipeline.models import ChapterIntent, ScenePlan
from factory.pipeline.validators import SceneCoverageValidator


def test_scene_coverage_requires_every_required_event() -> None:
    intent = ChapterIntent(
        chapter_no=7,
        title="试剑",
        chapter_goal="主角通过试剑",
        required_events=["主角登台", "主角获胜"],
    )
    scenes = [
        ScenePlan(
            scene_id="ch0007.sc01",
            scene_no=1,
            scene_goal="主角登台",
            covers_required_events=["主角登台"],
        )
    ]
    result = SceneCoverageValidator().validate(intent, scenes)
    assert not result.valid
    assert "required event not covered: 主角获胜" in result.issues


def test_scene_coverage_accepts_complete_plan() -> None:
    intent = ChapterIntent(chapter_no=1, title="起", required_events=["相遇"])
    scenes = [
        ScenePlan(
            scene_id="ch0001.sc01",
            scene_no=1,
            scene_goal="让两人相遇",
            covers_required_events=["相遇"],
        )
    ]
    assert SceneCoverageValidator().validate(intent, scenes).valid


def test_legacy_plan_write_workflow_inserts_scene_planner() -> None:
    stages = expand_stages(["chapter_planner", "chapter_writer"])
    assert "scene_planner" in stages


def test_writer_receives_intent_and_validated_scene_plan(workflow) -> None:
    workflow.run(("world_builder", "character", "novel_architect", "outline", "volume_planner"))
    result = workflow.run(("chapter_planner", "chapter_writer"))
    completed = {(item["stage"], item["status"]) for item in result["pipeline"]["log"]}
    assert ("scene_planner", "ok") in completed
    assert result["chapter_plan"]["intent"]["chapter_no"] == 1
    assert result["chapter_plan"]["scenes"]
