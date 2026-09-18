from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from factory.schema.contracts import StoryBible


class ImportMode(str, Enum):
    CREATE = "create"
    MERGE = "merge"
    REPLACE = "replace"


class ImportIssue(BaseModel):
    level: Literal["warning", "error"]
    code: str
    message: str
    entity_id: str = ""
    source_heading: str = ""
    source_line: int | None = None


class ImportChange(BaseModel):
    action: Literal["add", "modify", "conflict", "delete_candidate", "unchanged"]
    entity_type: str
    entity_id: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    message: str = ""


class ParsedFramework(BaseModel):
    source_file: str
    source_hash: str
    operation_id: str
    bible: StoryBible
    issues: list[ImportIssue] = Field(default_factory=list)


class ImportPreview(BaseModel):
    book_id: str
    mode: ImportMode
    source_file: str
    source_hash: str
    operation_id: str
    bible: StoryBible
    issues: list[ImportIssue] = Field(default_factory=list)
    changes: list[ImportChange] = Field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not any(issue.level == "error" for issue in self.issues)

    def summary(self) -> dict[str, int]:
        result = {key: 0 for key in ("add", "modify", "conflict", "delete_candidate", "unchanged")}
        for change in self.changes:
            result[change.action] += 1
        return result

