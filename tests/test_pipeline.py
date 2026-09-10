"""Chapter production pipeline: structured I/O, revision cap, resume."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from factory.agents.quality import ContinuityAgent, ReviewerAgent
from factory.pipeline.chapter import decide, expand_stages
from factory.pipeline.models import ChapterDraft, ContinuityReport, PipelineError, ReviewResult
from factory.workflow import SimpleWorkflow
from helpers import seed_book, settings_for


class ContractTest(unittest.TestCase):
    def test_review_result_from_legacy_issues(self) -> None:
        result = ReviewResult.from_llm(
            {"score": 55, "passed": False, "issues": [{"severity": "hard", "message": "没钩子"}, {"severity": "warn", "message": "略平"}]}
        )
        self.assertFalse(result.passed)
        self.assertIn("没钩子", result.must_fix)
        dumped = result.model_dump(by_alias=True)
        self.assertIn("pass", dumped)
        self.assertFalse(dumped["pass"])

    def test_continuity_buckets_and_severity(self) -> None:
        report = ContinuityReport.from_llm(
            {"issues": [], "passed": True, "notes": "ok"},
            extra=[{"severity": "hard", "type": "dead_character_appears", "dimension": "character", "message": "死人现身"}],
        )
        self.assertEqual(report.severity, "hard")
        self.assertFalse(report.passed)
        self.assertEqual(len(report.character_conflicts), 1)

    def test_decision_requests_revision(self) -> None:
        draft = ChapterDraft(ch_no=1, title="t", body="body")
        decision = decide(
            ContinuityReport(),
            ReviewResult(score=40, must_fix=["加钩子"], passed=False),
            draft,
            0,
        )
        self.assertEqual(decision.action, "revision")
        self.assertIsNotNone(decision.request)
        self.assertIn("加钩子", decision.request.must_fix)


class PipelineTest(unittest.TestCase):
    def test_happy_path_writes_checkpoint_and_record(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            seed_book(tmp)
            result = SimpleWorkflow(settings_for(tmp), "demo").run()
            chapter = tmp / "demo" / "chapters" / "ch001"
            self.assertTrue((chapter / "pipeline.json").exists())
            self.assertTrue((chapter / "record.json").exists())
            self.assertTrue((chapter / "final.md").exists())
            self.assertEqual(result["pipeline"]["status"], "completed")
            self.assertEqual(result["pipeline"]["revision_attempts"], 0)
            self.assertIn("pass", result["review"])

    def test_revision_loop_then_pass(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            seed_book(tmp)
            wf = SimpleWorkflow(settings_for(tmp), "demo")
            wf.run(("world_builder", "character", "novel_architect", "outline", "volume_planner"))
            calls = {"n": 0}
            real = ReviewerAgent.execute

            def once_fail(self, state):
                result = real(self, state)
                calls["n"] += 1
                if calls["n"] == 1:
                    result["review"] = ReviewResult(score=40, problems=["弱"], must_fix=["加钩子"], passed=False).model_dump(by_alias=True)
                return result

            with patch.object(ReviewerAgent, "execute", once_fail):
                result = wf.run(("chapter_planner", "chapter_writer", "continuity", "reviewer", "revision", "memory"))
            self.assertEqual(result["revision_attempts"], 1)
            self.assertEqual(result["status"], "revised")
            self.assertEqual(calls["n"], 2)

    def test_max_revisions_saves_anyway(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            seed_book(tmp)
            settings = replace(settings_for(tmp), max_revisions=2)
            wf = SimpleWorkflow(settings, "demo")
            wf.run(("world_builder", "character", "novel_architect", "outline", "volume_planner"))
            real = ReviewerAgent.execute

            def always_fail(self, state):
                result = real(self, state)
                result["review"] = {
                    "score": 10,
                    "problems": ["弱"],
                    "must_fix": ["重写"],
                    "pass": False,
                    "strengths": [],
                    "optional_fix": [],
                }
                return result

            with patch.object(ReviewerAgent, "execute", always_fail):
                result = wf.run(("chapter_planner", "chapter_writer", "continuity", "reviewer", "revision", "memory"))
            self.assertEqual(result["status"], "max_revisions")
            self.assertEqual(result["revision_attempts"], 2)
            self.assertTrue((tmp / "demo" / "chapters" / "ch001" / "final.md").exists())

    def test_resume_from_failed_stage(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            seed_book(tmp)
            wf = SimpleWorkflow(settings_for(tmp), "demo")
            wf.run(("world_builder", "character", "novel_architect", "outline", "volume_planner"))
            calls = {"n": 0}
            real = ContinuityAgent.execute

            def boom_once(self, state):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise RuntimeError("injected failure")
                return real(self, state)

            with patch.object(ContinuityAgent, "execute", boom_once):
                with self.assertRaises(PipelineError) as caught:
                    wf.run(("chapter_planner", "chapter_writer", "continuity", "reviewer", "revision", "memory"))
            self.assertEqual(caught.exception.stage, "continuity_check")
            checkpoint = tmp / "demo" / "chapters" / "ch001" / "pipeline.json"
            self.assertTrue(checkpoint.exists())
            wf2 = SimpleWorkflow(settings_for(tmp), "demo")
            wf2.resume = True
            with patch.object(ContinuityAgent, "execute", boom_once):
                result = wf2.run(("chapter_planner", "chapter_writer", "continuity", "reviewer", "revision", "memory"))
            self.assertEqual(result["pipeline"]["status"], "completed")
            self.assertEqual(calls["n"], 2)
            writer_starts = [
                item for item in result["pipeline"]["log"] if item["stage"] == "chapter_writer" and item["status"] == "start"
            ]
            self.assertEqual(len(writer_starts), 1)
            self.assertTrue((tmp / "demo" / "chapters" / "ch001" / "final.md").exists())

    def test_expand_stages_reviewer_only(self) -> None:
        wanted = expand_stages(["reviewer"])
        self.assertIn("quality_review", wanted)
        self.assertNotIn("continuity_check", wanted)
        self.assertNotIn("save", wanted)

    def test_expand_stages_revision_only(self) -> None:
        wanted = expand_stages(["revision"])
        self.assertIn("revision", wanted)
        self.assertNotIn("decision", wanted)
        self.assertNotIn("save", wanted)


if __name__ == "__main__":
    unittest.main()
