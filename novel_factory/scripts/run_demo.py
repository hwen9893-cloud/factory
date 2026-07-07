from __future__ import annotations

import json
import shutil
from pathlib import Path

from novel_factory.acs_novel_factory.center.knowledge import KnowledgeStore
from novel_factory.acs_novel_factory.center.model import ModelClient
from novel_factory.acs_novel_factory.skills.novel import (
    ChapterSkill,
    DialogueSkill,
    ExportSkill,
    OutlineSkill,
    PlotSkill,
)
from novel_factory.acs_novel_factory.skills.qa import ConsistencySkill


ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / "runs" / "run_0001"


def prepare_run_dir() -> None:
    if RUN_DIR.exists():
        shutil.rmtree(RUN_DIR)
    RUN_DIR.mkdir(parents=True)


def write_json(name: str, payload: dict) -> None:
    (RUN_DIR / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    prepare_run_dir()

    model_client = ModelClient(ROOT / "acs_novel_factory" / "center" / "model" / "profiles.json")
    knowledge_store = KnowledgeStore(ROOT / "knowledge")
    knowledge_snapshot = knowledge_store.snapshot()

    seed_state = {
        "story_seed": "灵根残缺少年在宗门试炼中被逼入绝境，借旧伤中残留的古剑灵息反击。",
        "volume_no": 1,
        "target_chapters": 3,
        "knowledge_snapshot": knowledge_snapshot,
        "input_ids": ["knowledge.character.0001", "knowledge.realm.0001", "knowledge.sect.0001"],
    }
    write_json("input_seed.json", seed_state)

    outline = OutlineSkill(RUN_DIR, model_client, knowledge_store).run(seed_state)
    plot = PlotSkill(RUN_DIR, model_client, knowledge_store).run({"outline": outline, "ch_no": 1})
    chapter = ChapterSkill(RUN_DIR, model_client, knowledge_store).run(
        {"plot": plot, "knowledge_snapshot": knowledge_snapshot}
    )
    polished = DialogueSkill(RUN_DIR, model_client, knowledge_store).run(
        {"chapter": chapter, "knowledge_snapshot": knowledge_snapshot}
    )
    qa_report = ConsistencySkill(RUN_DIR, model_client, knowledge_store).run(
        {"chapter": polished, "knowledge_snapshot": knowledge_snapshot}
    )
    export = ExportSkill(RUN_DIR, model_client, knowledge_store).run({"chapter": polished})

    summary = {
        "run_id": "run_0001",
        "status": "done" if qa_report["qa_passed"] else "needs_human",
        "artifacts": {
            "outline": "novel_outline.json",
            "plot": "novel_plot.json",
            "chapter": "novel_chapter.json",
            "dialogue": "novel_dialogue.json",
            "qa": "qa_consistency.json",
            "export": export["export_path"],
        },
        "qa_passed": qa_report["qa_passed"],
        "issue_count": len(qa_report["issues"]),
    }
    write_json("run_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
