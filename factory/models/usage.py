"""Per-call model usage. Metadata only — no prompts, bodies, or API keys."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class UsageRecord:
    timestamp: str
    agent: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency: float
    success: bool
    retry_count: int
    estimated_cost: float | None
    book_id: str = ""


@dataclass(frozen=True)
class UsageBucket:
    name: str
    calls: int
    tokens: int
    cost: float | None


@dataclass(frozen=True)
class UsageReport:
    calls: int
    tokens: int
    cost: float | None
    failed: int
    by_agent: tuple[UsageBucket, ...]
    by_model: tuple[UsageBucket, ...]


class UsageStore:
    """SQLite append log for model calls. Safe to share across CLI invocations."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def record(self, item: UsageRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO calls(
                    timestamp, agent, provider, model,
                    input_tokens, output_tokens, total_tokens,
                    latency, success, retry_count, estimated_cost, book_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.timestamp,
                    item.agent,
                    item.provider,
                    item.model,
                    int(item.input_tokens),
                    int(item.output_tokens),
                    int(item.total_tokens),
                    float(item.latency),
                    1 if item.success else 0,
                    int(item.retry_count),
                    item.estimated_cost,
                    item.book_id,
                ),
            )

    def summarize(self, *, since: str, book_id: str | None = None) -> UsageReport:
        where = "timestamp >= ?"
        params: list[Any] = [since]
        if book_id:
            where += " AND book_id = ?"
            params.append(book_id)
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT COUNT(*),
                       COALESCE(SUM(total_tokens), 0),
                       SUM(estimated_cost),
                       SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END)
                FROM calls
                WHERE {where}
                """,
                params,
            ).fetchone()
            calls = int(row[0] or 0)
            tokens = int(row[1] or 0)
            cost = None if row[2] is None else float(row[2])
            failed = int(row[3] or 0)
            by_agent = self._buckets(conn, "agent", where, params)
            by_model = self._buckets(conn, "model", where, params)
        return UsageReport(
            calls=calls,
            tokens=tokens,
            cost=cost,
            failed=failed,
            by_agent=by_agent,
            by_model=by_model,
        )

    def recent(self, *, book_id: str | None = None, limit: int = 5) -> tuple[UsageRecord, ...]:
        """Latest calls. Metadata only — no prompts, bodies, or keys."""
        where = "1=1"
        params: list[Any] = []
        if book_id:
            where = "book_id = ?"
            params.append(book_id)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT timestamp, agent, provider, model,
                       input_tokens, output_tokens, total_tokens,
                       latency, success, retry_count, estimated_cost, book_id
                FROM calls
                WHERE {where}
                ORDER BY id DESC
                LIMIT ?
                """,
                [*params, int(limit)],
            ).fetchall()
        return tuple(
            UsageRecord(
                timestamp=str(row[0] or ""),
                agent=str(row[1] or ""),
                provider=str(row[2] or ""),
                model=str(row[3] or ""),
                input_tokens=int(row[4] or 0),
                output_tokens=int(row[5] or 0),
                total_tokens=int(row[6] or 0),
                latency=float(row[7] or 0),
                success=bool(row[8]),
                retry_count=int(row[9] or 0),
                estimated_cost=None if row[10] is None else float(row[10]),
                book_id=str(row[11] or ""),
            )
            for row in rows
        )

    def today_start(self) -> str:
        now = datetime.now().astimezone()
        return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")

    @classmethod
    def for_data_dir(cls, data_dir: Path) -> "UsageStore":
        return cls(data_dir / "usage.sqlite")

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS calls (
                    id INTEGER PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    latency REAL NOT NULL,
                    success INTEGER NOT NULL,
                    retry_count INTEGER NOT NULL,
                    estimated_cost REAL,
                    book_id TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_calls_ts ON calls(timestamp)")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _buckets(
        self,
        conn: sqlite3.Connection,
        column: str,
        where: str,
        params: list[Any],
    ) -> tuple[UsageBucket, ...]:
        if column not in {"agent", "model"}:
            raise ValueError(f"invalid bucket column: {column}")
        rows = conn.execute(
            f"""
            SELECT {column},
                   COUNT(*),
                   COALESCE(SUM(total_tokens), 0),
                   SUM(estimated_cost)
            FROM calls
            WHERE {where}
            GROUP BY {column}
            ORDER BY SUM(total_tokens) DESC, {column} ASC
            """,
            params,
        ).fetchall()
        return tuple(
            UsageBucket(
                name=str(row[0] or "—"),
                calls=int(row[1] or 0),
                tokens=int(row[2] or 0),
                cost=None if row[3] is None else float(row[3]),
            )
            for row in rows
        )


def now_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def format_report(report: UsageReport) -> str:
    lines = [
        "today",
        f"  calls    {report.calls}" + (f"  ({report.failed} failed)" if report.failed else ""),
        f"  tokens   {report.tokens}",
        f"  cost     {_money(report.cost)}",
        "",
        "agent",
    ]
    lines.extend(_bucket_lines(report.by_agent))
    lines.append("")
    lines.append("model")
    lines.extend(_bucket_lines(report.by_model))
    return "\n".join(lines)


def _bucket_lines(rows: tuple[UsageBucket, ...]) -> list[str]:
    if not rows:
        return ["  —"]
    width = max(len(item.name) for item in rows)
    width = max(width, 8)
    return [
        f"  {item.name:<{width}}  {item.calls:>4}  {item.tokens:>8}  {_money(item.cost)}"
        for item in rows
    ]


def _money(value: float | None) -> str:
    if value is None:
        return "—"
    return f"${value:.4f}"
