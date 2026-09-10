"""Offline demo: full mock pipeline with no live model calls."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch

from factory.cli import main
from factory.demo import REQUIRED, run_offline_demo


def test_offline_demo_writes_chapter(tmp_path: Path) -> None:
    report = run_offline_demo(tmp_path)
    assert report.ok, f"missing={report.missing} status={report.pipeline_status}"
    assert report.pipeline_status in {"completed", "passed"}
    assert report.chapter_path.exists()
    text = report.chapter_path.read_text(encoding="utf-8")
    assert "陆沉" in text or "主角" in text
    for rel in REQUIRED:
        assert (report.book_dir / rel).exists(), rel
    assert (tmp_path / "usage.sqlite").exists()


def test_cli_demo_keeps_files(tmp_path: Path) -> None:
    buf = io.StringIO()
    err = io.StringIO()
    with patch("sys.stdout", buf), patch("sys.stderr", err):
        code = main(["demo", "--out", str(tmp_path)])
    assert code == 0, err.getvalue()
    out = buf.getvalue()
    assert "demo passed" in out
    assert "no live API" in out
    assert (tmp_path / "demo" / "chapters" / "ch001" / "final.md").exists()
