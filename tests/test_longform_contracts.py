from __future__ import annotations

import unittest

from factory.schema.contracts import (
    CharacterKnowledgeState,
    FactSource,
    GoldenFingerDefinition,
    StoryBible,
    StoryState,
    StoryStateDelta,
)
from factory.schema.ids import stable_id


class LongformContractTest(unittest.TestCase):
    def test_fact_priority(self) -> None:
        ordered = [
            FactSource.HARD_RULE,
            FactSource.AUTHOR,
            FactSource.FRAMEWORK,
            FactSource.FINAL_CHAPTER,
            FactSource.AGENT_INFERENCE,
        ]
        self.assertEqual([item.priority for item in ordered], [500, 400, 300, 200, 100])

    def test_stable_id_preserves_explicit_and_stabilizes_chinese(self) -> None:
        self.assertEqual(stable_id("char", "陆沉", "char.luchen"), "char.luchen")
        self.assertEqual(stable_id("char", "陆沉"), stable_id("char", "陆沉"))
        self.assertTrue(stable_id("char", "陆沉").startswith("char."))

    def test_old_project_defaults_are_valid(self) -> None:
        bible = StoryBible.model_validate({"world": {}, "characters": []})
        state = StoryState.model_validate({})
        self.assertEqual(bible.schema_version, 2)
        self.assertEqual(state.state_version, 0)
        self.assertEqual(bible.golden_fingers, [])
        self.assertEqual(state.hook_ledger, [])

    def test_golden_finger_separates_definition_and_state(self) -> None:
        definition = GoldenFingerDefinition(
            id="gf.sword",
            name="古剑",
            can_do=["分析剑招"],
            cannot_do=["凭空提升境界"],
        )
        bible = StoryBible(golden_fingers=[definition])
        state = StoryState.model_validate(
            {"golden_fingers": {"gf.sword": {"golden_finger_id": "gf.sword", "usage_count": 2}}}
        )
        self.assertEqual(bible.golden_fingers[0].cannot_do, ["凭空提升境界"])
        self.assertEqual(state.golden_fingers["gf.sword"].usage_count, 2)

    def test_state_delta_and_knowledge_defaults(self) -> None:
        delta = StoryStateDelta(operation_id="chapter-0001-finalize-v1", chapter_no=1, base_state_version=0)
        knowledge = CharacterKnowledgeState(character_id="char.hero")
        self.assertEqual(delta.character_changes, [])
        self.assertEqual(knowledge.known_facts, [])


if __name__ == "__main__":
    unittest.main()
