"""Deterministic checks shared by planning and final validation."""

from __future__ import annotations

from dataclasses import dataclass, field

from factory.pipeline.models import ChapterIntent, ScenePlan


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    issues: tuple[str, ...] = field(default_factory=tuple)


class SceneCoverageValidator:
    def validate(self, intent: ChapterIntent, scenes: list[ScenePlan]) -> ValidationResult:
        issues: list[str] = []
        covered = {event for scene in scenes for event in scene.covers_required_events}
        for event in intent.required_events:
            if event not in covered:
                issues.append(f"required event not covered: {event}")
        for scene in scenes:
            if not scene.scene_goal:
                issues.append(f"scene has no goal: {scene.scene_id}")
            if not scene.covers_required_events and not scene.payoff and not scene.exit_hook:
                issues.append(f"scene is unrelated to intent: {scene.scene_id}")
        ids = [scene.scene_id for scene in scenes]
        if len(ids) != len(set(ids)):
            issues.append("duplicate scene_id")
        return ValidationResult(valid=not issues, issues=tuple(issues))

