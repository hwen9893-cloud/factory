"""Outline tree + preview. Talks only to FactoryService."""

from __future__ import annotations

from nicegui import ui

from factory.gui.adapters import nav_tree
from factory.gui.theme import empty_book, page_header
from factory.gui.presentation.nav import NavNode
from factory.service import FactoryService
from factory.settings import Settings


def build_outline(*, book_id: str | None, settings: Settings) -> None:
    service = FactoryService(settings)
    resolved = service.resolve_book(book_id)
    if not resolved:
        page_header("Outline", "outline")
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
            page_header("Outline", "outline")
            with ui.element("div").classes("page-body"):
                ui.label("左树右预览。状态看是否已有 final.md。点章节可去写作页。").classes("muted")
                with ui.element("div").classes("split-wide"):
                    with ui.element("div").classes("side-list"):
                        ui.button(tree.label, on_click=lambda: self._show_book()).props("flat dense no-caps").classes(
                            "side-item"
                        )
                        for volume in tree.children:
                            ui.label(volume.label).classes("muted mt-3")
                            for chapter in volume.children:
                                mark = {"final": "已写", "draft": "草稿", "failed": "失败"}.get(chapter.status, "未写")
                                ui.button(
                                    f"{chapter.label} · {mark}",
                                    on_click=lambda _e=None, node=chapter: self._show_chapter(node),
                                ).props("flat dense no-caps").classes("side-item")
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
            lines.append("\n**Volume beats**")
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
            f"状态：`{detail.get('status')}`",
            "",
            f"- hook：{chapter.get('hook') or '—'}",
            f"- 焦点人物：{', '.join(chapter.get('char_focus') or []) or '—'}",
        ]
        events = chapter.get("key_events") or []
        if events:
            lines.append("\n**Key events**")
            for item in events:
                lines.append(f"- {item}")
        if plan:
            lines.append(f"\n**本章任务** {plan.get('goal') or ''}")
            for scene in plan.get("scenes") or []:
                if isinstance(scene, dict):
                    lines.append(f"- 场景：{scene.get('goal') or scene.get('location') or ''}")
        lines.append(f"\n[打开 Chapter Studio](/studio)")
        self.preview.set_content("\n".join(str(item) for item in lines))
