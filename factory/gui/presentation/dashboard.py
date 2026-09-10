"""Dashboard view mapping. Inputs are Core DTOs; no storage or workflow calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from factory.models.usage import UsageRecord
from factory.service import BookStatus, ChapterResult


@dataclass(frozen=True)
class DashboardView:
    title: str
    volume_no: int
    volume_title: str
    completed: int
    outlined: int
    next_chapter: int | None
    last_final: int | None
    last_title: str
    word_count: int
    writer_label: str
    open_threads: tuple[str, ...]
    recent_tasks: tuple[str, ...]
    has_outline: bool


def volume_title(outline: dict[str, Any], volume_no: int) -> str:
    for volume in outline.get("volumes") or []:
        if int(volume.get("volume_no") or 0) == volume_no:
            return str(volume.get("title") or "")
    return ""


def open_thread_lines(
    plot_threads: list[dict[str, Any]],
    memory_threads: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> tuple[str, ...]:
    lines: list[str] = []
    seen: set[str] = set()
    for item in plot_threads:
        if str(item.get("status") or "open") not in {"open", "active"}:
            continue
        text = str(item.get("title") or item.get("text") or "").strip()
        if text and text not in seen:
            seen.add(text)
            lines.append(text)
        if len(lines) >= limit:
            return tuple(lines)
    for item in memory_threads:
        if str(item.get("status") or "open") not in {"open", "active", ""}:
            continue
        text = str(item.get("text") or "").strip()
        if text and text not in seen:
            seen.add(text)
            lines.append(text)
        if len(lines) >= limit:
            break
    return tuple(lines[:limit])


def usage_lines(records: tuple[UsageRecord, ...]) -> tuple[str, ...]:
    return tuple(
        f"{item.agent} · {'ok' if item.success else 'fail'} · {item.model}" for item in records
    )


def build_dashboard_view(
    *,
    status: BookStatus,
    outline: dict[str, Any],
    finals: tuple[ChapterResult, ...],
    writer_label: str,
    open_threads: tuple[str, ...],
    recent_tasks: tuple[str, ...],
) -> DashboardView:
    word_count = sum(item.word_count for item in finals if item.source == "final")
    last_title = ""
    if status.last_final:
        match = next((item for item in finals if item.ch_no == status.last_final), None)
        last_title = match.title if match else ""
    return DashboardView(
        title=status.title,
        volume_no=status.volume,
        volume_title=volume_title(outline, status.volume),
        completed=status.completed,
        outlined=status.outlined,
        next_chapter=status.next_chapter,
        last_final=status.last_final,
        last_title=last_title,
        word_count=word_count,
        writer_label=writer_label,
        open_threads=open_threads,
        recent_tasks=recent_tasks,
        has_outline=status.has_outline,
    )
