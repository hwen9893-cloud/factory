"""Non-secret desktop preferences stored below the user data directory."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any

from factory.platform.paths import application_paths


@dataclass(frozen=True)
class DesktopPreferences:
    language: str = "zh-CN"
    theme: str = "dark"
    project_path: str = ""
    model_provider: str = ""
    model_path: str = ""
    api_endpoint: str = ""
    window_width: int = 1280
    window_height: int = 820
    last_project: str = ""
    first_run: bool = True

    def updated(self, **changes: Any) -> "DesktopPreferences":
        return replace(self, **changes)


def load_preferences(path: Path | None = None) -> DesktopPreferences:
    target = path or application_paths().preferences_file
    if not target.exists():
        return DesktopPreferences()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return DesktopPreferences()
    if not isinstance(payload, dict):
        return DesktopPreferences()
    allowed = {field.name for field in fields(DesktopPreferences)}
    clean = {key: value for key, value in payload.items() if key in allowed}
    try:
        return DesktopPreferences(**clean)
    except (TypeError, ValueError):
        return DesktopPreferences()


def save_preferences(preferences: DesktopPreferences, path: Path | None = None) -> Path:
    target = path or application_paths().preferences_file
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(asdict(preferences), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return target

