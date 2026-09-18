"""Launch Novel Factory GUI. Import only from the CLI `studio` command."""

from __future__ import annotations

import os
from pathlib import Path

from factory.settings import Settings, load_settings


def run_studio(
    *,
    book: str | None = None,
    host: str = "127.0.0.1",
    port: int = 8080,
    settings: Settings | None = None,
    show: bool = True,
    native: bool = False,
    favicon: Path | None = None,
    window_size: tuple[int, int] = (1280, 820),
) -> None:
    try:
        from nicegui import ui
    except ImportError as exc:
        raise ImportError('Chapter Studio needs NiceGUI. pip install -e ".[gui]"') from exc

    from factory.gui.bible import build_bible
    from factory.gui.framework import build_framework
    from factory.gui.dashboard import build_dashboard
    from factory.gui.memory import build_memory
    from factory.gui.logs import build_logs
    from factory.gui.models import build_models_page
    from factory.gui.outline import build_outline
    from factory.gui.settings import build_settings
    from factory.gui.studio import build_studio
    from factory.gui.welcome import build_welcome

    resolved = settings or load_settings()

    @ui.page("/")
    def dashboard_page() -> None:
        if os.environ.get("STORYFACTORY_DESKTOP") == "1" and build_welcome(settings=resolved):
            return
        build_dashboard(book_id=book, settings=resolved)

    @ui.page("/studio")
    def studio_page() -> None:
        build_studio(book_id=book, settings=resolved)

    @ui.page("/bible")
    def bible_page() -> None:
        build_bible(book_id=book, settings=resolved)

    @ui.page("/outline")
    def outline_page() -> None:
        build_outline(book_id=book, settings=resolved)

    @ui.page("/framework")
    def framework_page() -> None:
        build_framework(book_id=book, settings=resolved)

    @ui.page("/memory")
    def memory_page() -> None:
        build_memory(book_id=book, settings=resolved)

    @ui.page("/models")
    def models_page() -> None:
        build_models_page(settings=resolved)

    @ui.page("/logs")
    def logs_page() -> None:
        build_logs(book_id=book, settings=resolved)

    @ui.page("/settings")
    def settings_page() -> None:
        build_settings(book_id=book, settings=resolved)

    run_args = {
        "host": host,
        "title": "Story Factory · AI 小说创作工作台",
        "reload": False,
        "show": show and not native,
        "native": native,
        "favicon": str(favicon) if favicon and favicon.exists() else None,
    }
    if native:
        run_args["window_size"] = window_size
        run_args["fullscreen"] = False
    else:
        run_args["port"] = port
    ui.run(**run_args)


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="factory-gui", description="Novel Factory GUI")
    parser.add_argument("--book", "-b", default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)
    run_studio(book=args.book, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
