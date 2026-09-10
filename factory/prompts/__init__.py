"""Load Markdown prompt templates. Placeholders are {{variable}}; no Jinja2."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

PROMPTS_ROOT = Path(__file__).resolve().parent

REQUIRED_HEADINGS = (
    "Role",
    "Objective",
    "Input",
    "Requirements",
    "Constraints",
    "Output Format",
)

_H1 = re.compile(r"^#\s+(.+?)\s*$")


class PromptError(FileNotFoundError):
    """Raised when a prompt template cannot be found or parsed."""


class PromptManager:
    """Resolve a prompt name to a Markdown file, then load() / render() it."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or PROMPTS_ROOT

    def load(self, name: str) -> dict[str, str]:
        """Return `{system, user}`. `# Role` is system; other H1 sections are user."""
        return markdown_to_messages(self._find(name).read_text(encoding="utf-8"))

    def load_sections(self, name: str) -> dict[str, str]:
        """Return H1 heading → body."""
        return split_markdown_sections(self._find(name).read_text(encoding="utf-8"))

    def render(self, name: str, **values: Any) -> dict[str, str]:
        loaded = self.load(name)
        bound = alias_variables(values)
        return {
            "system": substitute(loaded["system"], bound),
            "user": substitute(loaded["user"], bound),
        }

    def _find(self, name: str) -> Path:
        path = (self.root / name.strip().replace("\\", "/")).with_suffix(".md")
        if path.exists():
            return path
        raise PromptError(f"prompt not found: {name} (looked under {self.root})")


def split_markdown_sections(text: str) -> dict[str, str]:
    """Split a Markdown prompt on H1 headings. Insertion order is document order."""
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        match = _H1.match(line)
        if match:
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = match.group(1).strip()
            buf = []
        else:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


def markdown_to_messages(text: str) -> dict[str, str]:
    """`# Role` → system. Remaining H1 sections stay in the user message, in order."""
    sections = split_markdown_sections(text)
    if not sections:
        return {"system": "", "user": text.strip()}
    role_key = next((key for key in sections if key.lower() == "role"), None)
    system = sections.get(role_key, "").strip() if role_key else ""
    if not system:
        return {"system": "", "user": text.strip()}
    parts: list[str] = []
    for heading, body in sections.items():
        if heading == role_key:
            continue
        chunk = f"# {heading}"
        if body:
            chunk += f"\n{body}"
        parts.append(chunk)
    return {"system": system, "user": "\n\n".join(parts).strip()}


def alias_variables(values: dict[str, Any]) -> dict[str, Any]:
    """Fill canonical template keys from older extra_vars names when missing."""
    merged = dict(values)
    _fill(merged, "story_title", "title")
    _fill(merged, "world_context", "canon", "world")
    _fill(
        merged,
        "character_context",
        "relevant_characters",
        "present_characters",
        "character_state",
        "characters",
    )
    _fill(merged, "plot_context", "plot_threads", "outline", "architecture")
    if _blank(merged.get("chapter_plan")):
        merged["chapter_plan"] = merged.get("chapter_outline") or merged.get("volume_chapter") or ""
    if _blank(merged.get("recent_context")):
        recent = merged.get("recent_chapters") if "recent_chapters" in merged else merged.get("recent_summaries")
        tail = merged.get("prev_tail") or ""
        if not _blank(recent) and not _blank(tail):
            merged["recent_context"] = f"{_stringify(recent)}\n\n上章文末：\n{_stringify(tail)}"
        else:
            merged["recent_context"] = recent if not _blank(recent) else tail
    return merged


def substitute(template: str, values: dict[str, Any]) -> str:
    """Replace {{key}} tokens. Leaves unmatched braces intact (unlike str.format)."""
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + str(key) + "}}", _stringify(value))
    return rendered


def _fill(merged: dict[str, Any], dest: str, *sources: str) -> None:
    if not _blank(merged.get(dest)):
        return
    for src in sources:
        if src in merged and not _blank(merged.get(src)):
            merged[dest] = merged[src]
            return
    merged.setdefault(dest, "")


def _blank(value: Any) -> bool:
    return value is None or value == ""


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return yaml.safe_dump(value, allow_unicode=True, sort_keys=False).strip()
    return str(value)
