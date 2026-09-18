"""Outline tree + preview. Talks only to FactoryService."""

from __future__ import annotations

from nicegui import ui

from factory.gui.adapters import nav_tree
from factory.gui.components import page_intro, status_badge
from factory.gui.theme import empty_book, page_header
from factory.gui.presentation.nav import NavNode
from factory.service import FactoryService
from factory.settings import Settings


def build_outline(*, book_id: str | None, settings: Settings) -> None:
    service = FactoryService(settings)
    resolved = service.resolve_book(book_id)
    if not resolved:
        page_header("章节大纲", "outline")
        empty_book()
        return
    OutlinePage(service, resolved).render()


class OutlinePage:
    def __init__(self, service: FactoryService, book_id: str) -> None:
        self.service = service
        self.book_id = book_id
        self.preview: Any = None

    def render(self) -> None:
        tree = nav_tree(self.service, self.book_id)
        with ui.element("div").classes("page-shell"):
            page_header("章节大纲", "outline", project=tree.label)
            with ui.element("div").classes("page-body"):
                with ui.element("div").classes("content-frame"):
                    intro = page_intro("章节大纲", "按卷浏览故事结构、关键事件和章节状态，并从预览直接进入创作。")
                    with intro:
                        with ui.element("div").classes("page-actions"):
                            ui.button("进入创作", on_click=lambda: ui.navigate.to("/studio"), icon="edit_note").props("unelevated no-caps")
                    with ui.element("div").classes("split-wide"):
                        with ui.element("div").classes("side-list"):
                            ui.button(tree.label, on_click=lambda: self._show_book(), icon="auto_stories").props("flat dense no-caps").classes("side-item")
                            for volume in tree.children:
                                vol_title = volume.label.split("  ", 1)[1] if "  " in volume.label else ""
                                vol_label = f"第 {volume.volume_no or 1} 卷" + (f" · {vol_title}" if vol_title else "")
                                ui.label(vol_label).classes("muted mt-3")
                                for chapter in volume.children:
                                    mark = {"final": "已定稿", "draft": "草稿", "failed": "失败"}.get(chapter.status, "待创作")
                                    ch_title = chapter.label.split("  ", 1)[1] if "  " in chapter.label else ""
                                    ch_label = f"第 {chapter.ch_no or 0} 章" + (f" · {ch_title}" if ch_title else "")
                                    ui.button(f"{ch_label} · {mark}", on_click=lambda _e=None, node=chapter: self._show_chapter(node)).props("flat dense no-caps").classes("side-item")
                        with ui.element("div").classes("panel-card"):
                            self.preview = ui.markdown("").classes("inspect-block")
        self._show_book()

    def _show_book(self) -> None:
        detail = self.service.outline_detail(self.book_id)
        arch = detail.get("architecture") or {}
        outline = detail.get("outline") or {}
        lines = [
            f"# {outline.get('title') or self.book_id}",
            "",
            str(arch.get("premise") or outline.get("premise") or arch.get("theme") or "_尚无总纲_"),
        ]
        beats = arch.get("volume_beats") or outline.get("volume_beats") or []
        if beats:
            lines.append("\n**分卷节拍**")
            for item in beats:
                lines.append(f"- {item}")
        self.preview.set_content("\n".join(lines))

    def _show_chapter(self, node: NavNode) -> None:
        if not node.ch_no:
            return
        detail = self.service.outline_detail(self.book_id, ch_no=node.ch_no, volume_no=node.volume_no)
        chapter = detail.get("chapter") or {}
        plan = detail.get("plan") or {}
        lines = [
            f"# {chapter.get('title') or node.label}",
            "",
            f"状态：`{ {'final': '已定稿', 'draft': '草稿', 'failed': '失败'}.get(str(detail.get('status')), '待创作') }`",
            "",
            f"- 开篇钩子：{chapter.get('hook') or '—'}",
            f"- 焦点人物：{', '.join(chapter.get('char_focus') or []) or '—'}",
        ]
        events = chapter.get("key_events") or []
        if events:
            lines.append("\n**关键事件**")
            for item in events:
                lines.append(f"- {item}")
        if plan:
            lines.append(f"\n**本章任务** {plan.get('goal') or ''}")
            for scene in plan.get("scenes") or []:
                if isinstance(scene, dict):
                    lines.append(f"- 场景：{scene.get('goal') or scene.get('location') or ''}")
        lines.append("\n[进入创作工作台 →](/studio)")
        self.preview.set_content("\n".join(str(item) for item in lines))
