"""Searchable model-call run history. Metadata only; no prompts or secrets."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from factory.gui.components import empty_state, page_intro, section_header, status_badge
from factory.gui.theme import page_header
from factory.service import FactoryService
from factory.settings import Settings
from factory.platform.paths import application_paths
from factory.platform.system import open_directory


def build_logs(*, book_id: str | None, settings: Settings) -> None:
    service = FactoryService(settings)
    resolved = service.resolve_book(book_id)
    LogsPage(service, resolved).render()


class LogsPage:
    def __init__(self, service: FactoryService, book_id: str | None) -> None:
        self.service = service
        self.book_id = book_id
        self.rows = service.recent_usage(book_id=book_id, limit=100)
        self.box: Any = None
        self.query = ""
        self.level = "all"

    def render(self) -> None:
        with ui.element("div").classes("page-shell"):
            page_header("运行记录", "logs", project=self.book_id or "全部项目")
            with ui.element("div").classes("page-body"):
                with ui.element("div").classes("content-frame"):
                    intro = page_intro("运行记录", "查看模型调用状态、耗时与 Token 用量。这里只保留元数据，不记录正文、提示词或密钥。")
                    with intro:
                        with ui.element("div").classes("page-actions"):
                            ui.button("打开日志目录", on_click=lambda: open_directory(application_paths().logs), icon="folder_open").props("outline no-caps")
                    with ui.row().classes("w-full items-center gap-2"):
                        ui.input(placeholder="搜索模型、提供商或 Agent", on_change=lambda e: self._search(e.value)).props("outlined dense clearable prepend-icon=search").classes("flex-1")
                        ui.select({"all": "全部级别", "success": "成功", "error": "失败"}, value="all", on_change=lambda e: self._filter(e.value)).props("outlined dense emit-value map-options").classes("w-36")
                    section_header("最近调用", f"最多显示 100 条 · 共 {len(self.rows)} 条")
                    self.box = ui.element("div").classes("panel-card")
                    self._paint()

    def _search(self, value: Any) -> None:
        self.query = str(value or "").lower()
        self._paint()

    def _filter(self, value: Any) -> None:
        self.level = str(value or "all")
        self._paint()

    def _paint(self) -> None:
        visible = [r for r in self.rows if (self.level == "all" or (self.level == "success") == r.success) and self.query in f"{r.agent} {r.provider} {r.model}".lower()]
        self.box.clear()
        with self.box:
            if not visible:
                empty_state("暂无匹配记录", "调整筛选条件，或先运行一次生成任务。", icon="receipt_long")
                return
            for item in visible:
                with ui.row().classes("w-full items-center no-wrap py-2").style("border-bottom:1px solid var(--border-soft)"):
                    status_badge("成功" if item.success else "失败", "success" if item.success else "danger")
                    with ui.column().classes("gap-0 flex-1 min-w-0"):
                        ui.label(f"{item.agent} · {item.model}").classes("text-sm")
                        ui.label(f"{item.provider} · {item.timestamp}").classes("muted mono")
                    ui.label(f"{item.total_tokens:,} tokens").classes("muted mono")
                    ui.label(f"{item.latency:.1f}s").classes("muted mono w-16 text-right")
