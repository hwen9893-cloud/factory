"""Dashboard — progress snapshot. Talks only to FactoryService / adapters."""

from __future__ import annotations

from queue import Empty, Queue
from threading import Thread
from typing import Any

from nicegui import ui

from factory.gui.adapters import dashboard_view
from factory.gui.components import metric_card, notify_error, page_intro, section_header, status_badge
from factory.gui.presentation.dashboard import DashboardView
from factory.gui.theme import empty_book, page_header
from factory.service import FactoryService
from factory.settings import Settings


def build_dashboard(*, book_id: str | None, settings: Settings) -> None:
    service = FactoryService(settings)
    resolved = service.resolve_book(book_id)
    if not resolved:
        page_header("首页", "dashboard")
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
            page_header("首页", "dashboard", project=snap.title)
            with ui.element("div").classes("page-body"):
                with ui.element("div").classes("content-frame"):
                    intro = page_intro("创作概览", "集中查看项目进度、模型状态和最近任务，并快速继续当前创作。")
                    with intro:
                        with ui.element("div").classes("page-actions"):
                            ui.button("进入创作工作台", on_click=lambda: ui.navigate.to("/studio"), icon="edit_note").props("unelevated no-caps")
                    with ui.element("div").classes("stat-grid"):
                        metric_card(snap.title, "当前项目", icon="auto_stories")
                        vol = f"第 {snap.volume_no} 卷" + (f" · {snap.volume_title}" if snap.volume_title else "")
                        metric_card(vol, "当前进度", icon="menu_book")
                        metric_card(f"{snap.completed} / {snap.outlined or '—'}", "已完成章节", icon="task_alt", hint="已定稿 / 已规划")
                        metric_card(f"{snap.word_count:,}" if snap.word_count else "—", "累计字数", icon="format_align_left", hint="仅统计已定稿正文")
                    section_header("需要关注", "线索、模型与最近生成状态")
                    with ui.element("div").classes("card-grid"):
                        self._card("最近章节", self._recent_chapter(snap), "/studio", "history_edu")
                        self._card("当前创作模型", snap.writer_label, "/models", "smart_toy", badge="已启用")
                        self._card("未收束线索", self._lines(snap.open_threads) or "暂无开放线索", icon="device_hub")
                        self._card("最近任务", self._lines(snap.recent_tasks) or "暂无调用记录", "/logs", "schedule")
                    with ui.row().classes("items-center mt-5"):
                        ui.button("继续下一章", on_click=self._continue, icon="play_arrow").props("unelevated no-caps")
                        self.status_lbl = ui.label("准备就绪").classes("muted")
                        if not snap.has_outline:
                            status_badge("需要先生成小说架构", "warning")
        ui.timer(0.2, self._drain)

    def _card(self, title: str, body: str, href: str | None = None, icon: str = "info", badge: str = "") -> None:
        with ui.element("div").classes("info-card"):
            with ui.row().classes("w-full items-center no-wrap"):
                ui.icon(icon, size="17px").style("color:var(--muted)")
                ui.html(f"<h3 style='margin:0'>{title}</h3>")
                ui.space()
                if badge:
                    status_badge(badge, "success")
            ui.label(body).style("white-space: pre-wrap")
            if href:
                ui.link("查看详情 →", href).classes("card-link")

    def _recent_chapter(self, snap: DashboardView) -> str:
        if snap.last_final:
            return f"第 {snap.last_final} 章  {snap.last_title or ''} · 已定稿"
        if snap.next_chapter:
            return f"下一章：第 {snap.next_chapter} 章 · 待创作"
        return "尚未写章"

    def _lines(self, rows: tuple[str, ...]) -> str:
        return "\n".join(rows)

    def _continue(self) -> None:
        if self.busy:
            return
        self.busy = True
        self.status_lbl.text = "正在生成下一章…"

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
        self.status_lbl.text = message if kind == "ok" else "生成失败"
        if kind == "ok":
            ui.navigate.reload()
        else:
            notify_error(message)
