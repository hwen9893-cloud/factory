from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import Skill


class ExportSkill(Skill):
    name = "skill.novel.export"
    required_inputs = ("chapter",)
    required_outputs = ("export_path", "format")

    def generate(self, state: dict[str, Any]) -> dict[str, Any]:
        chapter = state["chapter"]
        export_dir = self.run_dir / "export"
        export_dir.mkdir(exist_ok=True)
        path = export_dir / f"chapter_{int(chapter['ch_no']):03d}.txt"
        text = f"{chapter['title']}\n\n{chapter['body']}\n"
        path.write_text(text, encoding="utf-8")
        return {
            "export_path": str(Path("export") / path.name),
            "format": "txt",
            "chapter_id": chapter["chapter_id"],
        }
