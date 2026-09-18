"""Stable identifiers for imported long-form story entities."""

from __future__ import annotations

import hashlib
import re
import unicodedata

_SAFE = re.compile(r"[^a-z0-9._-]+")


def stable_id(kind: str, name: str, explicit: str = "") -> str:
    """Prefer explicit IDs; otherwise derive a deterministic, readable identifier."""
    if explicit.strip():
        return explicit.strip()
    normalized = unicodedata.normalize("NFKC", name).strip().lower()
    ascii_slug = _SAFE.sub("-", normalized.encode("ascii", "ignore").decode()).strip("-._")
    if ascii_slug:
        return f"{kind}.{ascii_slug}"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return f"{kind}.{digest}"

