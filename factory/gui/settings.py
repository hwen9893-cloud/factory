"""Runtime settings. Keys stay in .env; this page never stores or displays them."""

from __future__ import annotations

from typing import Any

from nicegui import run, ui

from factory.gui.components import page_intro, section_header, status_badge
from factory.gui.presentation.catalog import build_provider_row
from factory.gui.theme import page_header
from factory.service import FactoryService
from factory.settings import Settings
from factory.platform.paths import application_paths
from factory.platform.preferences import load_preferences, save_preferences
from factory.platform.system import choose_directory, open_directory


def build_settings(*, book_id: str | None = None, settings: Settings) -> None:
    del book_id
    SettingsPage(FactoryService(settings)).render()


class SettingsPage:
    def __init__(self, service: FactoryService) -> None:
        self.service = service
        self.paths = application_paths()
        self.preferences = load_preferences(self.paths.preferences_file)
        self.project_path_label: Any = None
        self.model_path_label: Any = None

    def render(self) -> None:
        snap = self.service.runtime_settings()
        with ui.element("div").classes("page-shell"):
            page_header("系统设置", "settings")
            with ui.element("div").classes("page-body"):
              with ui.element("div").classes("content-frame"):
                intro = page_intro("系统设置", "调整生成、记忆与存储参数。修改会写入 config/local.yaml，API 密钥仍只保存在 .env。")
                with intro:
                    with ui.element("div").classes("page-actions"):
                        ui.button("保存设置", on_click=lambda: self._save(words, rounds, recent, tail, threads, chars, backend), icon="save").props("unelevated no-caps")
                section_header("基础配置")
                with ui.element("div").classes("form-grid"):
                    with ui.element("div").classes("info-card"):
                        ui.html("<h3>生成参数</h3>")
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
                        ui.html("<h3>记忆参数</h3>")
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
                        ui.html("<h3>当前模型</h3>")
                        ui.label(f"运行标识：{snap.provider_stamp or '—'}").classes("muted")
                        ui.label(f"默认模型：{snap.default_model or '—'}")
                        ui.link("前往模型分工 →", "/models").classes("card-link")
                    with ui.element("div").classes("info-card"):
                        ui.html("<h3>存储与服务</h3>")
                        ui.label(f"数据目录：{snap.data_dir}").classes("muted mono")
                        backend = ui.select(
                            {"json": "json", "sqlite": "sqlite"},
                            value=snap.storage_backend,
                            label="存储后端",
                        ).props("outlined dense emit-value map-options")
                        for status in self.service.provider_statuses():
                            row = build_provider_row(status)
                            with ui.row().classes("items-center gap-2"):
                                status_badge("已配置" if row.configured else "未配置", "success" if row.configured else "warning")
                                ui.label(row.display_name).classes("text-sm")
                        ui.label("安全提示：请勿在此页或配置文件中粘贴 API Key。").classes("muted")
                section_header("桌面端目录", "发布版数据写入用户目录，不写入安装目录")
                with ui.element("div").classes("panel-card"):
                    ui.label("项目数据目录").classes("text-sm")
                    self.project_path_label = ui.label(self.preferences.project_path or str(self.paths.projects)).classes("muted mono")
                    with ui.row().classes("items-center gap-2"):
                        ui.button("选择项目目录", on_click=self._choose_project_dir, icon="folder_open").props("outline no-caps")
                        ui.button("打开日志目录", on_click=lambda: open_directory(self.paths.logs), icon="article").props("flat no-caps")
                    ui.label("本地模型目录（仅保存路径，不会把模型打包进应用）").classes("text-sm mt-3")
                    self.model_path_label = ui.label(self.preferences.model_path or "未选择").classes("muted mono")
                    ui.button("选择模型目录", on_click=self._choose_model_dir, icon="folder_open").props("outline no-caps")

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
        ui.notify("设置已保存", type="positive", caption="已写入 config/local.yaml")

    async def _choose_project_dir(self) -> None:
        chosen = await run.io_bound(
            choose_directory,
            title="选择 Story Factory 项目数据目录",
            initial=self.paths.projects,
        )
        if not chosen:
            return
        self.preferences = self.preferences.updated(project_path=str(chosen))
        save_preferences(self.preferences, self.paths.preferences_file)
        self.project_path_label.text = str(chosen)
        ui.notify("项目目录已保存，重启后生效", type="positive")

    async def _choose_model_dir(self) -> None:
        chosen = await run.io_bound(
            choose_directory,
            title="选择本地模型目录",
            initial=None,
        )
        if not chosen:
            return
        self.preferences = self.preferences.updated(model_path=str(chosen))
        save_preferences(self.preferences, self.paths.preferences_file)
        self.model_path_label.text = str(chosen)
        ui.notify("模型路径已保存", type="positive")
