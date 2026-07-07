from __future__ import annotations

from typing import Any

from ..base import Skill


class OutlineSkill(Skill):
    name = "skill.novel.outline"
    required_inputs = ("story_seed", "volume_no")
    required_outputs = ("outline_id", "volume_no", "chapters")

    def generate(self, state: dict[str, Any]) -> dict[str, Any]:
        target_chapters = int(state.get("target_chapters", 3))
        chapters = []
        for chapter_no in range(1, target_chapters + 1):
            chapters.append(
                {
                    "ch_no": chapter_no,
                    "title": f"第{chapter_no}章 灵根初鸣",
                    "key_events": [
                        "主角遭遇宗门试炼压力",
                        "旧伤或秘密被迫暴露",
                        "以弱胜强，留下下一章钩子",
                    ],
                    "char_focus": ["knowledge.character.0001"],
                    "realm_progress": "炼气期前期 -> 炼气期中期" if chapter_no == 3 else "",
                    "爽点类型": "打脸/突破" if chapter_no == 3 else "压迫/反转",
                }
            )
        return {
            "outline_id": f"outline.v{state['volume_no']:03d}",
            "volume_no": state["volume_no"],
            "chapters": chapters,
        }
