"""Memory layers — read-only. Talks only to FactoryService."""

from __future__ import annotations

from nicegui import ui

from factory.gui.presentation.inspector import memory_layers_md
from factory.gui.theme import empty_book, page_header
from factory.service import FactoryService
from factory.settings import Settings


def build_memory(*, book_id: str | None, settings: Settings) -> None:
    service = FactoryService(settings)
    resolved = service.resolve_book(book_id)
    if not resolved:
        page_header("Memory", "memory")
        empty_book()
        return
    MemoryPage(service, resolved).render()


class MemoryPage:
    def __init__(self, service: FactoryService, book_id: str) -> None:
        self.service = service
        self.book_id = book_id

    def render(self) -> None:
        overview = self.service.memory_overview(self.book_id)
        plot = self.service.list_plot(self.book_id)
        with ui.element("div").classes("page-shell"):
            page_header("Memory", "memory")
            with ui.element("div").classes("page-body"):
                ui.label("模型实际带着的分层记忆。第一期只读；改设定去 Story Bible。").classes("muted")
                ui.markdown(memory_layers_md(overview, plot.get("foreshadowing") or [])).classes("inspect-block")
