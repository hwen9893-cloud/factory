from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class KnowledgeStore:
    """Lightweight JSON knowledge store for Sprint 0/Sprint 1."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def load(self, name: str) -> Any:
        path = self.root / f"{name}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def snapshot(self) -> dict[str, Any]:
        return {
            "characters": self.load("characters"),
            "realms": self.load("realms"),
            "sects": self.load("sects"),
            "timeline": self.load("timeline"),
        }
