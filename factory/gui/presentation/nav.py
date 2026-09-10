"""Pure nav tree mapping. Callers pass outline + statuses; this does not touch storage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NavNode:
    id: str
    label: str
    kind: str
    ch_no: int | None = None
    volume_no: int | None = None
    status: str = ""
    children: list[NavNode] = field(default_factory=list)


def chapter_numbers(outline: dict[str, Any]) -> tuple[int, ...]:
    numbers: list[int] = []
    for volume in outline.get("volumes") or []:
        for chapter in volume.get("chapters") or []:
            ch_no = int(chapter.get("ch_no") or 0)
            if ch_no:
                numbers.append(ch_no)
    return tuple(numbers)


def chapter_label(chapter: dict[str, Any]) -> str:
    ch_no = int(chapter.get("ch_no") or 0)
    title = str(chapter.get("title") or "").strip()
    if title.startswith(f"第{ch_no}章"):
        rest = title[len(f"第{ch_no}章") :].strip()
        return f"Chapter {ch_no}" + (f"  {rest}" if rest else "")
    if title:
        return f"Chapter {ch_no}  {title}"
    return f"Chapter {ch_no}"


def build_nav_tree(
    book_id: str,
    title: str,
    outline: dict[str, Any],
    statuses: dict[int, str],
) -> NavNode:
    volumes: list[NavNode] = []
    for volume in outline.get("volumes") or []:
        volume_no = int(volume.get("volume_no") or 1)
        vol_title = str(volume.get("title") or "")
        label = f"Volume {volume_no}" + (f"  {vol_title}" if vol_title else "")
        chapters = [
            NavNode(
                id=f"ch-{int(chapter.get('ch_no') or 0)}",
                label=chapter_label(chapter),
                kind="chapter",
                ch_no=int(chapter.get("ch_no") or 0),
                volume_no=volume_no,
                status=statuses.get(int(chapter.get("ch_no") or 0), "outlined"),
            )
            for chapter in volume.get("chapters") or []
            if int(chapter.get("ch_no") or 0)
        ]
        volumes.append(
            NavNode(
                id=f"vol-{volume_no}",
                label=label,
                kind="volume",
                volume_no=volume_no,
                children=chapters,
            )
        )
    if not volumes:
        volumes.append(NavNode(id="vol-1", label="Volume 1", kind="volume", volume_no=1))
    return NavNode(id=f"book-{book_id}", label=title, kind="book", children=volumes)
