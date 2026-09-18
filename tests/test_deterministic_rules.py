from __future__ import annotations

from factory.memory.types import ContextRequest
from factory.pipeline.models import ChapterIntent, ScenePlan
from factory.pipeline.rules import ContinuityRuleValidator
from factory.schema.contracts import (
    CharacterKnowledgeState,
    GoldenFingerDefinition,
    GoldenFingerState,
    Provenance,
    SourcedFact,
    StoryBible,
    StoryState,
)


def test_unknown_secret_spoken_by_pov_character_is_issue() -> None:
    bible = StoryBible(
        facts=[SourcedFact(id="secret.black_tower_origin", text="黑塔来自天外", provenance=Provenance())]
    )
    state = StoryState(
        character_knowledge={"char.a": CharacterKnowledgeState(character_id="char.a")}
    )
    issues = ContinuityRuleValidator().validate(
        body="他确信黑塔来自天外。",
        chapter_no=3,
        bible=bible,
        state=state,
        scenes=[ScenePlan(scene_id="s1", scene_no=1, pov="char.a", scene_goal="调查", exit_hook="发现线索")],
    )
    assert any(item["dimension"] == "KNOWLEDGE" for item in issues)


def test_known_secret_is_allowed() -> None:
    bible = StoryBible(facts=[SourcedFact(id="secret.origin", text="黑塔来自天外")])
    state = StoryState(
        character_knowledge={
            "char.a": CharacterKnowledgeState(character_id="char.a", secrets_known=["secret.origin"])
        }
    )
    issues = ContinuityRuleValidator().validate(
        body="他确信黑塔来自天外。",
        chapter_no=3,
        bible=bible,
        state=state,
        scenes=[ScenePlan(scene_id="s1", scene_no=1, pov="char.a", scene_goal="调查", exit_hook="发现线索")],
    )
    assert not any(item["dimension"] == "KNOWLEDGE" for item in issues)


def test_golden_finger_cooldown_is_deterministic_issue() -> None:
    bible = StoryBible(golden_fingers=[GoldenFingerDefinition(id="golden.sword", name="古剑")])
    state = StoryState(
        golden_fingers={
            "golden.sword": GoldenFingerState(golden_finger_id="golden.sword", cooldown_until=8)
        }
    )
    issues = ContinuityRuleValidator().validate(
        body="陆沉再次催动古剑。", chapter_no=7, bible=bible, state=state
    )
    assert any(item["type"] == "golden_finger_cooldown" for item in issues)


def test_context_retriever_keeps_hard_rules_under_small_budget(workflow) -> None:
    bundle = workflow.memory_retriever.retrieve(
        ContextRequest(
            chapter_no=1,
            chapter_plan={"chapter_no": 1, "title": "起"},
            scene_plan=[{"scene_id": "s1"}],
            token_budget=256,
        )
    )
    assert bundle.hard_rules == workflow.memory_store.load().canon.rules
    assert bundle.current_story_state
    assert bundle.chapter_intent["chapter_no"] == 1
