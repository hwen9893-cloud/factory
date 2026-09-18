"""Constrained semantic normalization after deterministic parsing."""

from __future__ import annotations

from collections.abc import Callable

from factory.framework.models import ParsedFramework


class FrameworkNormalizer:
    """Optional normalizer hook; never receives authority to replace locked facts."""

    def __init__(self, callback: Callable[[ParsedFramework], ParsedFramework] | None = None) -> None:
        self.callback = callback

    def normalize(self, parsed: ParsedFramework) -> ParsedFramework:
        return self.callback(parsed) if self.callback else parsed

