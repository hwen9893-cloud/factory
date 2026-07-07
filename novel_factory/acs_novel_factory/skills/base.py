from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class SkillError(Exception):
    """Base error for skill execution."""


class SchemaValidationError(SkillError):
    """Raised when a state object misses required fields."""


class Skill(ABC):
    name: str = "skill.unknown"
    required_inputs: tuple[str, ...] = ()
    required_outputs: tuple[str, ...] = ()

    def __init__(self, run_dir: Path, model_client: Any | None = None, knowledge_store: Any | None = None) -> None:
        self.run_dir = run_dir
        self.model_client = model_client
        self.knowledge_store = knowledge_store

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        started_at = time.time()
        self.validate_required(state, self.required_inputs, "input")
        result = self.generate(state)
        self.validate_required(result, self.required_outputs, "output")
        result.setdefault("lineage", self.lineage(state))
        self.write_artifact(result)
        self.write_log(started_at, result)
        return result

    @abstractmethod
    def generate(self, state: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def artifact_name(self) -> str:
        return self.name.replace("skill.", "").replace(".", "_") + ".json"

    def write_artifact(self, result: dict[str, Any]) -> None:
        path = self.run_dir / self.artifact_name()
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_log(self, started_at: float, result: dict[str, Any]) -> None:
        logs_dir = self.run_dir / "logs"
        logs_dir.mkdir(exist_ok=True)
        payload = {
            "skill": self.name,
            "artifact": self.artifact_name(),
            "elapsed_sec": round(time.time() - started_at, 3),
            "output_keys": sorted(result.keys()),
        }
        (logs_dir / f"{self.name.replace('.', '_')}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def lineage(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "skill": self.name,
            "model": getattr(self.model_client, "active_model", "mock"),
            "input_ids": state.get("input_ids", []),
            "params": state.get("params", {}),
        }

    def validate_required(self, payload: dict[str, Any], keys: tuple[str, ...], kind: str) -> None:
        missing = [key for key in keys if key not in payload or payload[key] in (None, "")]
        if missing:
            raise SchemaValidationError(f"{self.name} missing {kind} field(s): {', '.join(missing)}")
