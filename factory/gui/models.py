"""Models / API Settings page. Detects env var presence; never stores or displays secrets."""

from __future__ import annotations

from queue import Empty, Queue
from threading import Thread
from typing import Any, Callable

from nicegui import ui

from factory.gui.components import notify_error, page_intro, section_header, status_badge
from factory.gui.presentation.catalog import (
    ProfileAdvanced,
    ProviderRow,
    build_profile_advanced,
    ordered_provider_rows,
)
from factory.gui.presentation.model_options import (
    INHERIT_VALUE,
    ROLE_LABELS,
    build_model_options,
    build_role_options,
    profile_label,
    role_assigned_profile,
    role_inherits_default,
)
from factory.gui.theme import page_header
from factory.models.keys import key_configured
from factory.service import FactoryService
from factory.settings import Settings
from factory.platform.credentials import delete_api_key, store_api_key

# Phase 1: detect whether environment variables exist. Do not add a key input.
# A later GUI writer must use a secure store — never YAML, novel.json, Git, or logs.


def build_models_page(*, settings: Settings) -> None:
    ModelsPage(FactoryService(settings)).render()


class ModelsPage:
    def __init__(self, service: FactoryService) -> None:
        self.service = service
        self.role_widgets: dict[str, Any] = {}
        self.advanced: Any = None
        self.default_sel: Any = None

    def render(self) -> None:
        with ui.element("div").classes("models-shell"):
            page_header("AI 模型", "models")
            with ui.element("div").classes("models-body"):
                with ui.element("div").classes("content-frame"):
                    page_intro("模型与服务", "管理模型服务连接和各创作环节的模型分工。密钥始终保存在环境变量中，不会在界面显示。")
                    self._api_section()
                    self._assignment_section()

    def _api_section(self) -> None:
        section_header("模型服务", "绿色表示已配置；灰色表示尚未连接")
        with ui.element("div").classes("panel-card"):
            for row in ordered_provider_rows(self.service.provider_statuses()):
                self._api_row(row)
            ui.label("如需添加密钥，请编辑 .env 后重启工作台。请勿将密钥写入 YAML、JSON、Git 或普通日志。").classes("muted mt-3")

    def _api_row(self, row: ProviderRow) -> None:
        with ui.element("div").classes("api-row"):
            ui.element("span").classes("api-dot on" if row.configured else "api-dot off")
            ui.label(row.display_name).classes("api-name")
            state = "已配置" if row.configured else ("无需配置" if not row.env_hint or row.env_hint == "—" else "未配置")
            ui.label(state).classes("api-state")
            ui.label(row.env_hint).classes("api-env")
            result_lbl = ui.label("").classes("api-result")
            btn = ui.button("测试连接", icon="cable").props("outline dense no-caps")
            btn.on_click(lambda _e=None, name=row.name, label=result_lbl, button=btn: self._test(name, label, button))
            if row.env_hint and row.env_hint != "—":
                ui.button(icon="key", on_click=lambda _e=None, name=row.name: self._credential_dialog(name)).props("flat round dense").tooltip("安全配置 API Key")

    def _credential_dialog(self, provider: str) -> None:
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg"):
            ui.label(f"配置 {provider} API Key").classes("text-lg font-semibold")
            ui.label("密钥将保存到操作系统凭据库，不会写入 YAML、JSON 或日志。").classes("muted")
            secret = ui.input(label="API Key").props("outlined autofocus type=password").classes("w-full")
            with ui.row().classes("w-full justify-end"):
                ui.button("删除", on_click=lambda: self._delete_credential(provider, dialog)).props("flat color=negative no-caps")
                ui.button("取消", on_click=dialog.close).props("flat no-caps")
                ui.button("安全保存", on_click=lambda: self._save_credential(provider, secret.value, dialog)).props("unelevated no-caps")
        dialog.open()

    def _save_credential(self, provider: str, secret: Any, dialog: Any) -> None:
        try:
            store_api_key(provider, str(secret or ""))
        except Exception as exc:
            notify_error(str(exc))
            return
        dialog.close()
        ui.notify("API Key 已保存到系统凭据库", type="positive")

    def _delete_credential(self, provider: str, dialog: Any) -> None:
        delete_api_key(provider)
        dialog.close()
        ui.notify("已删除系统凭据", type="positive")

    def _test(self, provider: str, result_lbl: Any, btn: Any) -> None:
        btn.disable()
        result_lbl.text = "正在测试…"
        result_lbl.classes(remove="ok fail")
        box: Queue = Queue()

        def work() -> None:
            box.put(self.service.test_connection(provider))

        Thread(target=work, daemon=True).start()

        def poll() -> None:
            try:
                result = box.get_nowait()
            except Empty:
                return
            timer.active = False
            if result.ok:
                result_lbl.text = f"连接正常  ({result.latency_ms:.0f} ms)"
                result_lbl.classes(add="ok")
            else:
                result_lbl.text = "连接失败"
                result_lbl.classes(add="fail")
                notify_error(result.message)
            btn.enable()

        timer = ui.timer(0.15, poll)

    def _assignment_section(self) -> None:
        registry = self.service.registry
        section_header("模型分工", "默认模型用于未单独指定的创作环节")

        default_id = registry.default_model
        default_options = dict(build_model_options(registry))
        if default_id and default_id not in default_options:
            default_options = {default_id: profile_label(registry, default_id), **default_options}

        self.default_sel = (
            ui.select(default_options, value=default_id or None, label="默认模型")
            .props("outlined dense emit-value map-options")
            .classes("w-80")
            .on_value_change(lambda e: self._apply_default(e.value))
        )

        ui.label("按环节覆盖").classes("text-subtitle2 mt-5")
        with ui.row().classes("w-full text-caption muted"):
            ui.label("创作环节").classes("w-28")
            ui.label("提供商").classes("w-24")
            ui.label("使用模型").classes("flex-1")
        for role, label in ROLE_LABELS.items():
            profile_id = role_assigned_profile(registry, role)
            inherited = role_inherits_default(registry, role)
            try:
                provider = registry.get_model(profile_id).provider if profile_id else ""
            except KeyError:
                provider = ""
            with ui.row().classes("w-full items-center no-wrap"):
                ui.label({"Architect": "架构设计", "Planner": "章节规划", "Writer": "正文创作", "Reviewer": "质量审阅"}.get(label, label)).classes("w-28")
                ui.label(provider or "—").classes("w-24 muted")
                options = self._role_options(role)
                value = INHERIT_VALUE if inherited else profile_id
                select = (
                    ui.select(options, value=value)
                    .props("outlined dense emit-value map-options")
                    .classes("flex-1")
                    .on_value_change(self._role_handler(role))
                )
                self.role_widgets[role] = select

        with ui.expansion("高级配置", icon="tune").classes("w-full mt-4"):
            ui.label("查看服务地址、超时和密钥环境变量名。此处不显示密钥值。").classes("muted")
            self.advanced = ui.markdown("").classes("inspect-block")
        self._refresh_advanced()

    def _apply_default(self, value: Any) -> None:
        profile_id = str(value or "")
        if profile_id == self.service.settings.default_model:
            return
        self.service.set_default_model(profile_id, persist=True)
        self._paint_roles()
        self._refresh_advanced()

    def _role_handler(self, role: str) -> Callable[[Any], None]:
        def handler(e: Any) -> None:
            chosen = str(e.value or "")
            profile_id = None if chosen == INHERIT_VALUE else chosen
            registry = self.service.registry
            inherited = role_inherits_default(registry, role)
            current = role_assigned_profile(registry, role)
            already = (profile_id is None and inherited) or (
                profile_id == current and not inherited
            )
            if already:
                return
            self.service.set_role_model(role, profile_id, persist=True)
            self._paint_roles()

        return handler

    def _paint_roles(self) -> None:
        registry = self.service.registry
        for role in ROLE_LABELS:
            select = self.role_widgets.get(role)
            if select is None:
                continue
            select.options = self._role_options(role)
            select.value = (
                INHERIT_VALUE if role_inherits_default(registry, role) else role_assigned_profile(registry, role)
            )

    def _refresh_advanced(self) -> None:
        if self.advanced is None:
            return
        chosen = (self.default_sel.value if self.default_sel is not None else None) or self.service.settings.default_model
        if not chosen:
            self.advanced.set_content("_未选择 Default profile_")
            return
        try:
            spec = self.service.registry.get_model(str(chosen))
        except KeyError:
            self.advanced.set_content(f"_未知 profile `{chosen}`_")
            return
        extra = build_profile_advanced(
            spec, key_configured(spec.provider, spec.api_key_env or "")
        )
        self.advanced.set_content(_advanced_md(extra))

    def _role_options(self, role: str) -> dict[str, str]:
        options = build_role_options(self.service.registry, role)
        if INHERIT_VALUE in options:
            options[INHERIT_VALUE] = options[INHERIT_VALUE].replace("Inherit Default", "继承默认模型")
        return options


def _advanced_md(info: ProfileAdvanced) -> str:
    key = "无需配置" if not info.api_key_env else ("已配置" if info.key_configured else "未配置")
    lines = [
        f"**{info.display_name}** `{info.profile_id}`",
        "",
        f"- 提供商：`{info.provider}`",
        f"- 模型名称：`{info.model}`",
        f"- 随机性 Temperature：`{info.temperature}`",
        f"- 超时时间：`{info.timeout_sec}` 秒",
        f"- 最大输出 Token：`{info.max_tokens}`",
        f"- 最大重试次数：`{info.max_retries}`",
        f"- 密钥环境变量：`{info.api_key_env or '—'}`（{key}）",
        f"- 服务地址：`{info.base_url or '—'}`",
    ]
    return "\n".join(lines)
