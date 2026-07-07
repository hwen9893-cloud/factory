from __future__ import annotations

from typing import Any

from ..base import Skill


class DialogueSkill(Skill):
    name = "skill.novel.dialogue"
    required_inputs = ("chapter", "knowledge_snapshot")
    required_outputs = ("chapter_id", "body", "dialogue_notes")

    def generate(self, state: dict[str, Any]) -> dict[str, Any]:
        chapter = dict(state["chapter"])
        chapter["body"] = chapter["body"] + "\n\n“这一剑，我接下了。”他声音不高，却让演武场的喧哗慢慢低了下去。"
        chapter["word_count"] = len(chapter["body"])
        chapter["dialogue_notes"] = [
            {
                "character_id": "knowledge.character.0001",
                "voice_style": "克制、冷静、短句，不主动解释委屈",
            }
        ]
        return chapter
