from __future__ import annotations

from typing import Any

from ..base import Skill


class PlotSkill(Skill):
    name = "skill.novel.plot"
    required_inputs = ("outline", "ch_no")
    required_outputs = ("plot_id", "ch_no", "scenes")

    def generate(self, state: dict[str, Any]) -> dict[str, Any]:
        ch_no = int(state["ch_no"])
        return {
            "plot_id": f"plot.ch{ch_no:03d}",
            "ch_no": ch_no,
            "scenes": [
                {
                    "scene_no": 1,
                    "location": "knowledge.place.0001",
                    "pov_char": "knowledge.character.0001",
                    "present_chars": ["knowledge.character.0001", "knowledge.character.0002"],
                    "goal": "建立压迫局面，明确主角当前劣势",
                    "conflict": "外门弟子当众挑衅，逼主角暴露实力",
                    "pacing": "fast",
                    "爽点": "先抑后扬",
                    "word_budget": 900,
                },
                {
                    "scene_no": 2,
                    "location": "knowledge.place.0001",
                    "pov_char": "knowledge.character.0001",
                    "present_chars": ["knowledge.character.0001", "knowledge.character.0003"],
                    "goal": "揭示主角底牌和修炼代价",
                    "conflict": "使用禁术会牵动旧伤",
                    "pacing": "medium",
                    "爽点": "底牌显露",
                    "word_budget": 900,
                },
                {
                    "scene_no": 3,
                    "location": "knowledge.place.0001",
                    "pov_char": "knowledge.character.0001",
                    "present_chars": ["knowledge.character.0001", "knowledge.character.0002"],
                    "goal": "完成反击并留下更大危机",
                    "conflict": "胜利引来执事注意",
                    "pacing": "fast",
                    "爽点": "打脸",
                    "word_budget": 900,
                },
            ],
        }
