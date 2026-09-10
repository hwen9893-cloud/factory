"""Runtime settings. Keys stay in .env; this page never stores or displays them."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from factory.gui.presentation.catalog import build_provider_row
from factory.gui.theme import page_header
from factory.service import FactoryService
from factory.settings import Settings


def build_settings(*, book_id: str | None = None, settings: Settings) -> None:
    del book_id
    SettingsPage(FactoryService(settings)).render()


class SettingsPage:
    def __init__(self, service: FactoryService) -> None:
        self.service = service

    def render(self) -> None:
        snap = self.service.runtime_settings()
        with ui.element("div").classes("page-shell"):
            page_header("Settings", "settings")
            with ui.element("div").classes("page-body"):
                ui.label(
                    "生成与记忆参数写入 config/local.yaml。API Key 只在 .env；本页只显示是否已配置。"
                ).classes("muted")
                with ui.element("div").classes("card-grid"):
                    with ui.element("div").classes("info-card"):
                        ui.html("<h3>Generation</h3>")
                        words = ui.number(
                            label="目标字数",
                            value=snap.chapter_target_words,
                            format="%.0f",
                        ).classes("w-full")
                        rounds = ui.number(
                            label="最大改稿轮次",
                            value=snap.max_revision_rounds,
                            format="%.0f",
                        ).classes("w-full")
                    with ui.element("div").classes("info-card"):
                        ui.html("<h3>Memory</h3>")
                        recent = ui.number(
                            label="近章摘要数",
                            value=snap.recent_chapters,
                            format="%.0f",
                        ).classes("w-full")
                        tail = ui.number(
                            label="上章文末字数",
                            value=snap.prev_tail_chars,
                            format="%.0f",
                        ).classes("w-full")
                        threads = ui.number(
                            label="开放线索上限",
                            value=snap.max_open_threads,
                            format="%.0f",
                        ).classes("w-full")
                        chars = ui.number(
                            label="相关人物上限",
                            value=snap.max_relevant_characters,
                            format="%.0f",
                        ).classes("w-full")
                    with ui.element("div").classes("info-card"):
                        ui.html("<h3>Models</h3>")
                        ui.label(f"FACTORY_PROVIDER / stamp：{snap.provider_stamp or '—'}")
                        ui.label(f"Default profile：{snap.default_model or '—'}")
                        ui.link("去模型页改指派", "/models").classes("nav-link")
                    with ui.element("div").classes("info-card"):
                        ui.html("<h3>API / Storage</h3>")
                        ui.label(f"data_dir：{snap.data_dir}").classes("muted")
                        backend = ui.select(
                            {"json": "json", "sqlite": "sqlite"},
                            value=snap.storage_backend,
                            label="存储后端",
                        ).props("outlined dense emit-value map-options")
                        for status in self.service.provider_statuses():
                            row = build_provider_row(status)
                            ui.label(f"{row.display_name}: {row.state}").classes("text-sm")
                        ui.label("不在此页粘贴 API Key。").classes("muted")
                ui.button(
                    "Save",
                    on_click=lambda: self._save(words, rounds, recent, tail, threads, chars, backend),
                ).props("unelevated").classes("mt-4")

    def _save(
        self,
        words: Any,
        rounds: Any,
        recent: Any,
        tail: Any,
        threads: Any,
        chars: Any,
        backend: Any,
    ) -> None:
        self.service.save_runtime(
            chapter_target_words=int(words.value or 0),
            max_revision_rounds=int(rounds.value or 0),
            recent_chapters=int(recent.value or 0),
            prev_tail_chars=int(tail.value or 0),
            max_open_threads=int(threads.value or 0),
            max_relevant_characters=int(chars.value or 0),
            storage_backend=str(backend.value or "json"),
            persist=True,
        )
        ui.notify("已写入 config/local.yaml")
