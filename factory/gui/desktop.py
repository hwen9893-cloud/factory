"""Windows/macOS desktop launcher sharing the existing NiceGUI and Core."""

from __future__ import annotations

import logging
import multiprocessing
import os
import sys
import threading

from factory.platform.credentials import load_keys_into_environment
from factory.platform.logs import configure_file_logging
from factory.platform.paths import AppPaths, ensure_user_dirs, resource_path
from factory.platform.preferences import DesktopPreferences, load_preferences
from factory.platform.system import SingleInstance, show_error_dialog
from factory.settings import Settings

logger = logging.getLogger("factory.desktop")


def _configure_desktop_environment() -> tuple[AppPaths, DesktopPreferences]:
    paths = ensure_user_dirs()
    preferences = load_preferences(paths.preferences_file)
    os.environ.setdefault("STORYFACTORY_DESKTOP", "1")
    os.environ.setdefault("FACTORY_CONFIG", str(paths.settings_file))
    os.environ.setdefault("FACTORY_DATA_DIR", preferences.project_path or str(paths.projects))
    load_keys_into_environment()
    return paths, preferences


def _log_provider_state(settings: Settings) -> None:
    try:
        from factory.service import FactoryService

        service = FactoryService(settings)
        for status in service.provider_statuses():
            logger.info(
                "provider status name=%s enabled=%s configured=%s",
                status.name,
                status.enabled,
                status.configured,
            )
    except Exception:
        logger.exception("background provider check failed")


def main() -> int:
    multiprocessing.freeze_support()
    paths, preferences = _configure_desktop_environment()
    configure_file_logging(paths.log_file)
    instance = SingleInstance()
    if not instance.acquire():
        show_error_dialog("Story Factory", "Story Factory 已经在运行。")
        return 0
    try:
        from factory.gui.app import run_studio
        from factory.settings import load_settings

        settings = load_settings()
        threading.Thread(
            target=_log_provider_state,
            args=(settings,),
            daemon=True,
            name="provider-status-check",
        ).start()
        run_studio(
            settings=settings,
            native=True,
            favicon=resource_path("assets", "icons", "app.ico"),
            window_size=(preferences.window_width, preferences.window_height),
        )
        return 0
    except Exception as exc:
        logger.critical("desktop startup failed", exc_info=True)
        show_error_dialog(
            "Story Factory 遇到错误",
            "程序发生异常，但您的项目数据不会被删除。\n\n"
            f"{exc}\n\n详细信息已写入日志。",
            log_dir=paths.logs,
        )
        return 1
    finally:
        instance.release()


if __name__ == "__main__":
    sys.exit(main())
