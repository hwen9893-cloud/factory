"""Platform paths for immutable resources and writable user data."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

APP_DIR_NAME = "StoryFactory"


@dataclass(frozen=True)
class AppPaths:
    root: Path
    config: Path
    logs: Path
    cache: Path
    projects: Path
    database: Path
    runtime: Path

    @property
    def settings_file(self) -> Path:
        return self.config / "local.yaml"

    @property
    def preferences_file(self) -> Path:
        return self.config / "desktop.json"

    @property
    def log_file(self) -> Path:
        return self.logs / "storyfactory.log"


def application_paths(
    *,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> AppPaths:
    """Return writable locations without creating them.

    Optional arguments keep Windows, macOS and Linux behavior testable on any host.
    """
    platform_name = platform_name or sys.platform
    env = environ if environ is not None else os.environ
    user_home = home or Path.home()

    if platform_name == "win32":
        base = Path(env.get("LOCALAPPDATA") or user_home / "AppData" / "Local") / APP_DIR_NAME
    elif platform_name == "darwin":
        base = user_home / "Library" / "Application Support" / APP_DIR_NAME
    else:
        base = Path(env.get("XDG_DATA_HOME") or user_home / ".local" / "share") / APP_DIR_NAME

    return AppPaths(
        root=base,
        config=base / "config",
        logs=base / "logs",
        cache=base / "cache",
        projects=base / "projects",
        database=base / "database",
        runtime=base / "runtime",
    )


def ensure_user_dirs(paths: AppPaths | None = None) -> AppPaths:
    paths = paths or application_paths()
    for path in (
        paths.root,
        paths.config,
        paths.logs,
        paths.cache,
        paths.projects,
        paths.database,
        paths.runtime,
    ):
        path.mkdir(parents=True, exist_ok=True)
    if not paths.settings_file.exists():
        paths.settings_file.write_text("{}\n", encoding="utf-8")
    return paths


def resource_root() -> Path:
    """Resolve files in development and PyInstaller onedir/onefile builds."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[2]


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)

