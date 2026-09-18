"""Preview-first Markdown framework import page. Calls FactoryService only."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from nicegui import ui

from factory.gui.components import empty_state, notify_error, page_intro, status_badge
from factory.gui.theme import empty_book, page_header
from factory.service import FactoryService
from factory.settings import Settings


def build_framework(*, book_id: str | None, settings: Settings) -> None:
    service = FactoryService(settings)
    resolved = service.resolve_book(book_id)
    if not resolved:
        page_header("框架导入", "framework")
        empty_book()
        return
    FrameworkPage(service, resolved).render()


class FrameworkPage:
    def __init__(self, service: FactoryService, book_id: str) -> None:
        self.service = service
        self.book_id = book_id
        self.source: Path | None = None
        self.preview: dict[str, Any] | None = None
        self.mode = "merge"

    def render(self) -> None:
        with ui.element("div").classes("page-shell"):
            page_header("框架导入", "framework", project=self.book_id)
            with ui.element("div").classes("page-body"):
                with ui.element("div").classes("content-frame"):
                    page_intro("导入网络小说框架", "上传 Markdown，先查看校验与变更预览，确认后才写入 Story Bible。")
                    with ui.element("div").classes("panel-card"):
                        self.mode_select = ui.select(
                            {"merge": "合并（推荐）", "replace": "替换", "create": "创建"},
                            value="merge",
                            label="导入模式",
                            on_change=lambda event: setattr(self, "mode", str(event.value)),
                        ).classes("w-64")
                        ui.upload(on_upload=self._uploaded, label="选择 Markdown 文件", auto_upload=True).props(
                            'accept=".md,text/markdown,text/plain" flat bordered'
                        ).classes("w-full")
                    self.result_box = ui.element("div").classes("panel-card mt-4")
        self._paint_empty()

    def _uploaded(self, event: Any) -> None:
        try:
            data = event.content.read()
            suffix = Path(str(event.name or "framework.md")).suffix or ".md"
            handle = tempfile.NamedTemporaryFile(prefix="story-framework-", suffix=suffix, delete=False)
            handle.write(data)
            handle.close()
            self.source = Path(handle.name)
            self.preview = self.service.preview_framework(self.book_id, self.source, mode=self.mode)
            self._paint_preview()
        except Exception as exc:
            notify_error(str(exc))

    def _paint_empty(self) -> None:
        self.result_box.clear()
        with self.result_box:
            empty_state("等待框架文件", "文件不会在预览阶段写入项目。", icon="description")

    def _paint_preview(self) -> None:
        payload = self.preview or {}
        self.result_box.clear()
        with self.result_box:
            status_badge("校验通过" if payload.get("valid") else "校验失败", "success" if payload.get("valid") else "danger")
            ui.label(f"操作 ID：{payload.get('operation_id') or '—'}").classes("mono muted mt-2")
            summary = payload.get("summary") or {}
            ui.label(" · ".join(f"{key}: {summary.get(key, 0)}" for key in ("add", "modify", "conflict", "delete_candidate"))).classes("mt-3")
            for issue in payload.get("issues") or []:
                ui.label(f"[{issue.get('level')}] {issue.get('code')}: {issue.get('message')}").classes("muted")
            ui.button("确认导入", on_click=self._commit, icon="publish", disabled=not payload.get("valid")).props("unelevated no-caps").classes("mt-4")

    def _commit(self) -> None:
        if not self.source or not self.preview or not self.preview.get("valid"):
            return
        try:
            result = self.service.import_framework(self.book_id, self.source, mode=self.mode)
            ui.notify(f"框架已导入：{result['operation_id']}", type="positive")
            self.preview = self.service.preview_framework(self.book_id, self.source, mode=self.mode)
            self._paint_preview()
        except Exception as exc:
            notify_error(str(exc))
