"""Deterministic quality gates around model-based review and polishing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from factory.pipeline.models import ChapterIntent, ScenePlan
from factory.pipeline.validators import SceneCoverageValidator


@dataclass(frozen=True)
class FactDiff:
    category: str
    before: tuple[str, ...]
    after: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class FinalValidationResult:
    valid: bool
    issues: tuple[str, ...] = field(default_factory=tuple)
    fact_diffs: tuple[FactDiff, ...] = field(default_factory=tuple)


class FactDiffValidator:
    """Compare protected, structured terms before and after a style-only pass."""

    def compare(self, before: str, after: str, protected: dict[str, Iterable[str]] | None = None) -> tuple[FactDiff, ...]:
        changes: list[FactDiff] = []
        for category, raw_terms in (protected or {}).items():
            terms = tuple(dict.fromkeys(str(term) for term in raw_terms if str(term)))
            before_hits = tuple(term for term in terms if term in before)
            after_hits = tuple(term for term in terms if term in after)
            if before_hits != after_hits:
                changes.append(
                    FactDiff(
                        category=category,
                        before=before_hits,
                        after=after_hits,
                        message=f"style polish changed protected {category}: {before_hits} -> {after_hits}",
                    )
                )
        return tuple(changes)


class FinalValidator:
    def validate(
        self,
        *,
        corrected: str,
        polished: str,
        intent: ChapterIntent,
        scenes: list[ScenePlan],
        protected_facts: dict[str, Iterable[str]] | None = None,
    ) -> FinalValidationResult:
        issues = list(SceneCoverageValidator().validate(intent, scenes).issues)
        for forbidden in intent.forbidden_events:
            if forbidden and forbidden in polished:
                issues.append(f"forbidden event appears in final text: {forbidden}")
        diffs = FactDiffValidator().compare(corrected, polished, protected_facts)
        issues.extend(item.message for item in diffs)
        return FinalValidationResult(valid=not issues, issues=tuple(issues), fact_diffs=diffs)
