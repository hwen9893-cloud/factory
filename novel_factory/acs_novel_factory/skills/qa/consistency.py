from __future__ import annotations

from typing import Any

from ..base import Skill


class ConsistencySkill(Skill):
    name = "skill.qa.consistency"
    required_inputs = ("chapter", "knowledge_snapshot")
    required_outputs = ("qa_passed", "issues")

    def generate(self, state: dict[str, Any]) -> dict[str, Any]:
        chapter = state["chapter"]
        snapshot = state["knowledge_snapshot"]
        issues = []
        body = chapter.get("body", "")

        dead_names = [char["name"] for char in snapshot["characters"] if char.get("status") == "dead"]
        for name in dead_names:
            if name in body:
                issues.append(
                    {
                        "severity": "hard",
                        "type": "dead_character_appears",
                        "message": f"已死亡角色 {name} 出现在正文中，需要确认是否为回忆或错误复活。",
                    }
                )

        known_realms = {realm["name"] for realm in snapshot["realms"]}
        if "元婴" in body and "元婴期" not in known_realms:
            issues.append(
                {
                    "severity": "hard",
                    "type": "unknown_realm",
                    "message": "正文出现未登记境界：元婴。",
                }
            )

        if chapter.get("word_count", 0) < 500:
            issues.append(
                {
                    "severity": "warn",
                    "type": "short_chapter",
                    "message": "当前原型章节较短，Sprint 1 后需要提升到 1500-3000 字。",
                }
            )

        hard_count = sum(1 for issue in issues if issue["severity"] == "hard")
        return {
            "qa_passed": hard_count == 0,
            "issues": issues,
            "chapter_id": chapter.get("chapter_id"),
        }
