"""Non-blocking first-run page for packaged desktop builds."""

from __future__ import annotations

from typing import Any

from nicegui import run, ui

from factory.gui.components import notify_error
from factory.gui.theme import apply_theme
from factory.platform.paths import application_paths
from factory.platform.preferences import load_preferences, save_preferences
from factory.platform.system import choose_directory
from factory.service import FactoryService
from factory.settings import Settings


def build_welcome(*, settings: Settings) -> bool:
    paths = application_paths()
    preferences = load_preferences(paths.preferences_file)
    if not preferences.first_run:
        return False
    WelcomePage(FactoryService(settings)).render()
    return True


class WelcomePage:
    def __init__(self, service: FactoryService) -> None:
        self.service = service
        self.paths = application_paths()
        self.preferences = load_preferences(self.paths.preferences_file)
        self.project_label: Any = None
        self.model_label: Any = None
        self.provider: Any = None
        self.test_result: Any = None

    def render(self) -> None:
        apply_theme()
        with ui.column().classes("fixed inset-0 items-center justify-center p-6").style("background:var(--bg);color:var(--text)"):
            with ui.column().classes("panel-card w-full max-w-3xl gap-4").style("padding:28px"):
                ui.label("欢迎使用 Story Factory").classes("text-2xl font-semibold")
                ui.label("完成几个可选设置，或直接稍后配置。模型不可用不会阻止工作台启动。").classes("muted")
                with ui.stepper().props("vertical flat animated").classes("w-full") as stepper:
                    with ui.step("项目数据", icon="folder"):
                        self.project_label = ui.label(self.preferences.project_path or str(self.paths.projects)).classes("mono muted")
                        ui.button("选择项目数据目录", on_click=self._choose_project, icon="folder_open").props("outline no-caps")
                        with ui.stepper_navigation():
                            ui.button("下一步", on_click=stepper.next).props("unelevated no-caps")
                    with ui.step("AI 模型", icon="smart_toy"):
                        choices = {
                            item.name: item.name.upper()
                            for item in self.service.provider_statuses()
                            if item.name != "mock"
                        }
                        self.provider = ui.select(choices, value=self.preferences.model_provider or None, label="模型 Provider").props("outlined emit-value map-options").classes("w-full")
                        self.model_label = ui.label(self.preferences.model_path or "本地模型路径尚未选择（在线 API 可忽略）").classes("mono muted")
                        ui.button("选择本地模型目录", on_click=self._choose_model, icon="folder_open").props("outline no-caps")
                        with ui.stepper_navigation():
                            ui.button("下一步", on_click=stepper.next).props("unelevated no-caps")
                            ui.button("上一步", on_click=stepper.previous).props("flat no-caps")
                    with ui.step("测试连接", icon="cable"):
                        self.test_result = ui.label("连接测试是可选的，可在主界面随时重试。").classes("muted")
                        ui.button("测试所选 Provider", on_click=self._test_provider, icon="cable").props("outline no-caps")
                        with ui.stepper_navigation():
                            ui.button("下一步", on_click=stepper.next).props("unelevated no-caps")
                            ui.button("上一步", on_click=stepper.previous).props("flat no-caps")
                    with ui.step("完成", icon="check_circle"):
                        ui.label("设置已准备好。后续可在“系统设置”和“AI 模型”中调整。")
                        with ui.stepper_navigation():
                            ui.button("进入主界面", on_click=self._finish, icon="arrow_forward").props("unelevated no-caps")
                ui.button("稍后配置", on_click=self._finish).props("flat no-caps")

    async def _choose_project(self) -> None:
        chosen = await run.io_bound(
            choose_directory,
            title="选择 Story Factory 项目数据目录",
            initial=self.paths.projects,
        )
        if chosen:
            self.preferences = self.preferences.updated(project_path=str(chosen))
            save_preferences(self.preferences, self.paths.preferences_file)
            self.project_label.text = str(chosen)

    async def _choose_model(self) -> None:
        chosen = await run.io_bound(
            choose_directory,
            title="选择本地模型目录",
            initial=None,
        )
        if chosen:
            self.preferences = self.preferences.updated(model_path=str(chosen))
            save_preferences(self.preferences, self.paths.preferences_file)
            self.model_label.text = str(chosen)

    async def _test_provider(self) -> None:
        provider = str(self.provider.value or "")
        if not provider:
            ui.notify("请先选择 Provider", type="warning")
            return
        self.test_result.text = "正在测试…"
        result = await run.io_bound(self.service.test_connection, provider)
        if result.ok:
            self.test_result.text = f"连接正常（{result.latency_ms:.0f} ms）"
        else:
            self.test_result.text = "连接失败；仍可继续进入主界面。"
            notify_error(result.message)

    def _finish(self) -> None:
        provider = str(self.provider.value or "") if self.provider is not None else ""
        self.preferences = self.preferences.updated(
            model_provider=provider or self.preferences.model_provider,
            first_run=False,
        )
        save_preferences(self.preferences, self.paths.preferences_file)
        ui.navigate.to("/")
