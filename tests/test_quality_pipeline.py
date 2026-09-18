from __future__ import annotations

from factory.pipeline.models import ChapterIntent, ScenePlan
from factory.pipeline.quality import FactDiffValidator, FinalValidator


def _intent() -> ChapterIntent:
    return ChapterIntent(chapter_no=1, title="破局", required_events=["陆沉反击"], forbidden_events=["赵衡死亡"])


def _scenes() -> list[ScenePlan]:
    return [
        ScenePlan(
            scene_id="ch0001.sc01",
            scene_no=1,
            scene_goal="陆沉反击",
            covers_required_events=["陆沉反击"],
        )
    ]


def test_fact_diff_rejects_realm_changed_by_polisher() -> None:
    diffs = FactDiffValidator().compare(
        "陆沉仍是炼气境。",
        "陆沉已踏入筑基境。",
        {"cultivation": ["炼气境", "筑基境"]},
    )
    assert len(diffs) == 1
    assert diffs[0].category == "cultivation"


def test_final_validator_accepts_style_only_change() -> None:
    result = FinalValidator().validate(
        corrected="炼气境的陆沉挥剑反击。",
        polished="陆沉挥剑反击，仍在炼气境。",
        intent=_intent(),
        scenes=_scenes(),
        protected_facts={"cultivation": ["炼气境", "筑基境"], "character": ["陆沉"]},
    )
    assert result.valid


def test_final_validator_rejects_forbidden_event() -> None:
    result = FinalValidator().validate(
        corrected="陆沉反击。",
        polished="陆沉反击，赵衡死亡。",
        intent=_intent(),
        scenes=_scenes(),
    )
    assert not result.valid
    assert any("forbidden event" in issue for issue in result.issues)


def test_default_workflow_runs_polish_and_final_gate(workflow) -> None:
    result = workflow.run(
        (
            "world_builder",
            "character",
            "novel_architect",
            "outline",
            "volume_planner",
            "chapter_planner",
            "chapter_writer",
            "continuity",
            "reviewer",
            "content_revision",
            "style_polisher",
        )
    )
    completed = {(item["stage"], item["status"]) for item in result["pipeline"]["log"]}
    assert ("style_polish", "ok") in completed
    assert ("final_validate", "ok") in completed
