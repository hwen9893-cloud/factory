"""Deterministic parser for the standard Chinese novel-framework Markdown."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from factory.framework.models import ImportIssue, ParsedFramework
from factory.framework.references import FIELD_ALIASES, SECTION_ALIASES
from factory.schema.contracts import FactSource, Provenance, StoryBible, utc_now
from factory.schema.ids import stable_id

_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
_FIELD = re.compile(r"^[-*]\s+([^:：]+)[:：]\s*(.*?)\s*$")


@dataclass
class Node:
    title: str
    line: int
    lines: list[tuple[int, str]] = field(default_factory=list)
    children: list["Node"] = field(default_factory=list)


class FrameworkParser:
    def parse_file(self, path: Path) -> ParsedFramework:
        text = path.read_text(encoding="utf-8-sig")
        return self.parse(text, source_file=str(path))

    def parse(self, text: str, *, source_file: str = "网络小说框架.md") -> ParsedFramework:
        source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        operation_id = f"framework-{source_hash[:16]}"
        sections, issues = _sections(text)
        payload: dict[str, Any] = {"schema_version": 2}
        for section in sections:
            key = SECTION_ALIASES.get(section.title.strip())
            if not key:
                issues.append(ImportIssue(level="warning", code="UNKNOWN_SECTION", message=f"未知章节：{section.title}", source_heading=section.title, source_line=section.line))
                continue
            self._apply_section(payload, key, section, source_file, source_hash, operation_id, issues)
        try:
            bible = StoryBible.model_validate(payload)
        except Exception as exc:
            issues.append(ImportIssue(level="error", code="SCHEMA_ERROR", message=str(exc)))
            bible = StoryBible()
        return ParsedFramework(
            source_file=source_file,
            source_hash=source_hash,
            operation_id=operation_id,
            bible=bible,
            issues=issues,
        )

    def _apply_section(self, payload: dict[str, Any], key: str, node: Node, source_file: str, source_hash: str, operation_id: str, issues: list[ImportIssue]) -> None:
        fields = _fields(node.lines)
        paragraphs = _paragraphs(node.lines)
        if key == "meta":
            payload.update({FIELD_ALIASES.get(k, k): _scalar(v) for k, v in fields.items()})
            return
        if key == "world":
            world = payload.setdefault("world", {})
            world["summary"] = str(fields.get("摘要") or "\n".join(paragraphs))
            world["rules"] = _list(fields.get("规则") or fields.get("硬规则") or [])
            return
        if key == "cultivation":
            realms = []
            for child in node.children:
                item = self._entity(child, "realm", source_file, source_hash, operation_id)
                item["name"] = _entity_name(child.title)
                realms.append(item)
            payload.setdefault("world", {}).setdefault("cultivation", {})["realms"] = realms
            return
        if key in {"characters", "factions", "locations", "golden_fingers", "antagonist_stages", "main_plot_phases", "payoff_rules", "hook_rules"}:
            kind = {"characters": "char", "factions": "faction", "locations": "location", "golden_fingers": "golden", "antagonist_stages": "villain_stage", "main_plot_phases": "plot_phase", "payoff_rules": "payoff", "hook_rules": "hook"}[key]
            rows = [self._entity(child, kind, source_file, source_hash, operation_id) for child in node.children]
            if key == "characters":
                for child, item in zip(node.children, rows):
                    item["name"] = _entity_name(child.title)
            elif key in {"factions", "locations", "golden_fingers"}:
                for child, item in zip(node.children, rows):
                    item["name"] = _entity_name(child.title)
            elif key == "main_plot_phases":
                for child, item in zip(node.children, rows):
                    item.setdefault("phase", _entity_name(child.title))
            elif key in {"payoff_rules", "hook_rules"}:
                for child, item in zip(node.children, rows):
                    item.setdefault("type", _entity_name(child.title))
            if key in {"factions", "locations"}:
                payload.setdefault("world", {})[key] = rows
            else:
                payload[key] = rows
            return
        if key == "foreshadowing":
            rows = []
            for child in node.children:
                item = self._entity(child, "foreshadow", source_file, source_hash, operation_id)
                item.setdefault("clue", _entity_name(child.title))
                rows.append(item)
            payload[key] = rows
            return
        if key == "style_guide":
            payload[key] = {FIELD_ALIASES.get(k, k): _typed_value(FIELD_ALIASES.get(k, k), v) for k, v in fields.items()}
            return
        if key == "forbidden_rules":
            payload[key] = _list(fields.get("规则") or [text for _, text in node.lines if text.startswith(("- ", "* "))])
            return
        if key in {"volume_plans", "chapter_outlines"}:
            payload[key] = [self._entity(child, "volume" if key == "volume_plans" else "chapter", source_file, source_hash, operation_id) for child in node.children]

    def _entity(self, node: Node, kind: str, source_file: str, source_hash: str, operation_id: str) -> dict[str, Any]:
        raw = _fields(node.lines)
        item = {FIELD_ALIASES.get(key, key): _typed_value(FIELD_ALIASES.get(key, key), value) for key, value in raw.items()}
        name = _entity_name(node.title)
        item["id"] = stable_id(kind, name, str(item.get("id") or ""))
        now = utc_now()
        item["provenance"] = Provenance(
            source_type=FactSource.FRAMEWORK,
            source_id=item["id"],
            source_file=source_file,
            source_hash=source_hash,
            source_heading=node.title,
            source_line=node.line,
            imported_at=now,
            import_operation_id=operation_id,
            created_at=now,
            updated_at=now,
        ).model_dump(mode="json")
        return item


def _sections(text: str) -> tuple[list[Node], list[ImportIssue]]:
    roots: list[Node] = []
    current: Node | None = None
    child: Node | None = None
    issues: list[ImportIssue] = []
    for number, raw in enumerate(text.splitlines(), 1):
        match = _HEADING.match(raw)
        if match:
            level, title = len(match.group(1)), match.group(2).strip()
            if level == 1:
                current = Node(title=title, line=number)
                roots.append(current)
                child = None
            elif level == 2 and current:
                child = Node(title=title, line=number)
                current.children.append(child)
            continue
        target = child or current
        if target is not None and raw.strip():
            target.lines.append((number, raw.strip()))
    if not roots:
        issues.append(ImportIssue(level="error", code="NO_SECTIONS", message="未找到一级 Markdown 标题"))
    return roots, issues


def _fields(lines: list[tuple[int, str]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for _number, text in lines:
        match = _FIELD.match(text)
        if match:
            result[match.group(1).strip()] = match.group(2).strip()
    return result


def _paragraphs(lines: list[tuple[int, str]]) -> list[str]:
    return [text for _, text in lines if not _FIELD.match(text) and not text.startswith(("- ", "* "))]


def _entity_name(title: str) -> str:
    return re.split(r"[:：]", title, maxsplit=1)[-1].strip()


def _list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).removeprefix("- ").removeprefix("* ").strip() for item in value if str(item).strip()]
    return [item.strip() for item in re.split(r"[,，、;；|]", str(value)) if item.strip()]


def _scalar(value: Any) -> Any:
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    return text


_LIST_FIELDS = {"goals", "activation_conditions", "inputs", "outputs", "costs", "limitations", "forbidden_uses", "can_do", "cannot_do", "resources", "pressure_method", "required_events", "turning_points", "foreshadowing", "payoffs", "failure_consequences", "preferred_vocabulary", "banned_phrases"}
_INT_FIELDS = {"stage_no", "cooldown_chapters", "repetition_limit", "cooldown"}


def _typed_value(key: str, value: Any) -> Any:
    if key in _LIST_FIELDS:
        return _list(value)
    if key in _INT_FIELDS:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    if key in {"starting_state", "ending_state", "initial_state"}:
        return {"description": str(value)}
    return _scalar(value)

