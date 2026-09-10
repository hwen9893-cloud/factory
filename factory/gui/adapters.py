"""Compose FactoryService queries for GUI pages. No Workflow, no storage, no mutations."""

from __future__ import annotations

from factory.gui.presentation.model_options import profile_label
from factory.gui.presentation.dashboard import DashboardView, build_dashboard_view, open_thread_lines, usage_lines
from factory.gui.presentation.inspector import InspectorView, build_inspector_view
from factory.gui.presentation.nav import NavNode, build_nav_tree
from factory.service import FactoryService


def nav_tree(service: FactoryService, book_id: str) -> NavNode:
    status = service.book_status(book_id)
    outline = (service.outline_detail(book_id).get("outline") or {}) if status.has_outline else {}
    return build_nav_tree(book_id, status.title, outline, service.chapter_statuses(book_id))


def dashboard_view(service: FactoryService, book_id: str) -> DashboardView:
    status = service.book_status(book_id)
    outline = (service.outline_detail(book_id).get("outline") or {}) if status.has_outline else {}
    finals = []
    last_final = int(status.last_final or 0)
    for ch_no in range(1, last_final + 1):
        view = service.load_chapter(book_id, ch_no)
        if view.source == "final":
            finals.append(view)
    plot = service.list_plot(book_id)
    memory = service.memory_overview(book_id)
    writer = service.registry.assigned_model_name("chapter_writer", default="writer")
    return build_dashboard_view(
        status=status,
        outline=outline,
        finals=tuple(finals),
        writer_label=profile_label(service.registry, writer),
        open_threads=open_thread_lines(plot.get("threads") or [], memory.get("threads") or []),
        recent_tasks=usage_lines(service.recent_usage(book_id=book_id)),
    )


def inspector_view(service: FactoryService, book_id: str, ch_no: int) -> InspectorView:
    detail = service.outline_detail(book_id, ch_no=ch_no)
    return build_inspector_view(
        plan=detail.get("plan"),
        context=service.writer_context(book_id, ch_no),
        review=detail.get("review"),
        continuity=detail.get("continuity"),
        memory=service.memory_view(book_id, ch_no),
    )
