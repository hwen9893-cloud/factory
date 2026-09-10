"""Dashboard — progress snapshot. Talks only to FactoryService / adapters."""

from __future__ import annotations

from queue import Empty, Queue
from threading import Thread
from typing import Any

from nicegui import ui

from factory.gui.adapters import dashboard_view
from factory.gui.presentation.dashboard import DashboardView
from factory.gui.theme import empty_book, page_header
from factory.service import FactoryService
from factory.settings import Settings


def build_dashboard(*, book_id: str | None, settings: Settings) -> None:
    service = FactoryService(settings)
    resolved = service.resolve_book(book_id)
    if not resolved:
        page_header("Dashboard", "dashboard")
        empty_book()
        return
    DashboardPage(service, resolved).render()


class DashboardPage:
    def __init__(self, service: FactoryService, book_id: str) -> None:
        self.service = service
        self.book_id = book_id
        self.status_lbl: Any = None
        self.busy = False
        self.events: Queue = Queue()

    def render(self) -> None:
        snap = dashboard_view(self.service, self.book_id)
        with ui.element("div").classes("page-shell"):
            page_header("Dashboard", "dashboard")
            with ui.element("div").classes("page-body"):
                ui.label("写到哪了，下一步做什么。正文请到 Chapter Studio。").classes("muted")
                with ui.element("div").classes("stat-grid"):
                    self._stat(snap.title, "当前小说")
                    vol = f"卷{snap.volume_no}" + (f"  {snap.volume_title}" if snap.volume_title else "")
                    self._stat(vol, "当前卷")
                    self._stat(f"{snap.completed} / {snap.outlined or '—'}", "当前章节")
                    self._stat(str(snap.word_count) if snap.word_count else "—", "总字数（final.md）")
                with ui.element("div").classes("card-grid"):
                    self._card("最近章节", self._recent_chapter(snap), "/studio")
                    self._card("当前模型", f"Writer → {snap.writer_label}", "/models")
                    self._card("未收束线索", self._lines(snap.open_threads) or "暂无开放线索")
                    self._card("最近任务", self._lines(snap.recent_tasks) or "暂无调用记录")
                with ui.row().classes("items-center mt-4"):
                    ui.button("继续下一章", on_click=self._continue).props("unelevated")
                    self.status_lbl = ui.label("Ready").classes("muted")
                    if not snap.has_outline:
                        ui.label("需要先 factory architect").classes("muted")
        ui.timer(0.2, self._drain)

    def _stat(self, value: str, label: str) -> None:
        with ui.element("div").classes("stat-card"):
            ui.label(value).classes("value")
            ui.label(label).classes("label")

    def _card(self, title: str, body: str, href: str | None = None) -> None:
        with ui.element("div").classes("info-card"):
            ui.html(f"<h3>{title}</h3>")
            ui.label(body).style("white-space: pre-wrap")
            if href:
                ui.link("打开", href).classes("nav-link")

    def _recent_chapter(self, snap: DashboardView) -> str:
        if snap.last_final:
            return f"ch{snap.last_final:03d}  {snap.last_title or ''} · 已定稿"
        if snap.next_chapter:
            return f"下一章 ch{snap.next_chapter:03d} · 未写"
        return "尚未写章"

    def _lines(self, rows: tuple[str, ...]) -> str:
        return "\n".join(rows)

    def _continue(self) -> None:
        if self.busy:
            return
        self.busy = True
        self.status_lbl.text = "Running..."

        def work() -> None:
            try:
                result = self.service.continue_next(self.book_id)
                if result.get("done"):
                    self.events.put(("ok", "全书大纲章节已写完"))
                else:
                    self.events.put(("ok", f"完成第 {result.get('ch_no') or ''} 章"))
            except Exception as exc:
                self.events.put(("fail", str(exc)))

        Thread(target=work, daemon=True).start()

    def _drain(self) -> None:
        try:
            kind, message = self.events.get_nowait()
        except Empty:
            return
        self.busy = False
        self.status_lbl.text = message
        if kind == "ok":
            ui.navigate.reload()
