"""Deterministic continuity rules; semantic ambiguity remains with the model."""

from __future__ import annotations

from factory.pipeline.models import ChapterIntent, ScenePlan
from factory.pipeline.validators import SceneCoverageValidator
from factory.schema.contracts import StoryBible, StoryState


class ContinuityRuleValidator:
    def validate(
        self,
        *,
        body: str,
        chapter_no: int,
        bible: StoryBible,
        state: StoryState,
        intent: ChapterIntent | None = None,
        scenes: list[ScenePlan] | None = None,
    ) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        for cid, character in state.characters.items():
            name = str(character.get("name") or cid)
            if character.get("status") == "dead" and name and name in body:
                issues.append(_issue("hard", "dead_character_appears", "CHARACTER", f"已死亡角色 {name} 出现在正文中。"))

        pov_ids = {scene.pov for scene in scenes or [] if scene.pov}
        for fact in bible.facts:
            if not fact.text or fact.text not in body:
                continue
            if not (fact.id.startswith("secret.") or "秘密" in fact.id):
                continue
            for pov_id in pov_ids:
                knowledge = state.character_knowledge.get(pov_id)
                known = set(knowledge.known_facts + knowledge.secrets_known) if knowledge else set()
                if fact.id not in known and fact.text not in known:
                    issues.append(_issue("hard", "unknown_secret_used", "KNOWLEDGE", f"视角角色 {pov_id} 尚不知道秘密 {fact.id}。"))

        for definition in bible.golden_fingers:
            current = state.golden_fingers.get(definition.id)
            if not current or not definition.name or definition.name not in body:
                continue
            if current.cooldown_until is not None and chapter_no <= current.cooldown_until:
                issues.append(_issue("hard", "golden_finger_cooldown", "GOLDEN_FINGER", f"{definition.name} 冷却至第 {current.cooldown_until} 章，本章不可再次使用。"))

        if intent is not None:
            coverage = SceneCoverageValidator().validate(intent, scenes or [])
            issues.extend(_issue("hard", "required_event_uncovered", "SCENE_COVERAGE", message) for message in coverage.issues)

        for rule in bible.hook_rules:
            if not rule.type or rule.type not in body or not rule.cooldown:
                continue
            previous = [entry for entry in state.hook_ledger if entry.type == rule.type]
            if previous and chapter_no - previous[-1].chapter_no <= rule.cooldown:
                issues.append(_issue("warn", "hook_cooldown", "HOOK", f"Hook“{rule.type}”仍在冷却窗口。"))
        for rule in bible.payoff_rules:
            if not rule.type or rule.type not in body or not rule.cooldown_chapters:
                continue
            previous = [entry for entry in state.payoff_ledger if entry.type == rule.type]
            if previous and chapter_no - previous[-1].chapter_no <= rule.cooldown_chapters:
                issues.append(_issue("warn", "payoff_cooldown", "PAYOFF", f"爽点“{rule.type}”使用过于频繁。"))
        return issues


def _issue(severity: str, kind: str, dimension: str, message: str) -> dict[str, str]:
    return {"severity": severity, "type": kind, "dimension": dimension, "message": message}
