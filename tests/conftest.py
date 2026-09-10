"""Shared pytest fixtures. All tests stay offline (mock provider only)."""

from __future__ import annotations

from pathlib import Path

import pytest

from factory.models.providers import MockModelProvider
from factory.storage import BookRepository
from helpers import install_mock, seed_book, settings_for


@pytest.fixture
def book_root(tmp_path: Path) -> Path:
    seed_book(tmp_path)
    return tmp_path


@pytest.fixture
def settings(book_root: Path):
    return settings_for(book_root)


@pytest.fixture
def repo(book_root: Path) -> BookRepository:
    return BookRepository(book_root)


@pytest.fixture
def mock_provider() -> MockModelProvider:
    return MockModelProvider()


@pytest.fixture
def workflow(settings, mock_provider):
    from factory.workflow import SimpleWorkflow

    wf = SimpleWorkflow(settings, "demo")
    install_mock(wf.models, mock_provider)
    return wf
