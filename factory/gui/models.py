"""Models / API Settings page. Detects env var presence; never stores or displays secrets."""

from __future__ import annotations

from queue import Empty, Queue
from threading import Thread
from typing import Any, Callable

from nicegui import ui

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
            page_header("Models / API Settings", "models")
            with ui.element("div").classes("models-body"):
                self._api_section()
                self._assignment_section()

    def _api_section(self) -> None:
        ui.label("API").classes("text-h6")
        ui.label(
            "Keys live in .env / the process environment. This page never stores, logs, or displays secret values. "
            "Configured means the named env var is non-empty."
        ).classes("muted")

        for row in ordered_provider_rows(self.service.provider_statuses()):
            self._api_row(row)

        ui.label(
            "To add a key, edit .env (copy from .env.example) and restart Studio. "
            "Do not put keys in factory.yaml, config/local.yaml, or Git."
        ).classes("muted mt-3")

    def _api_row(self, row: ProviderRow) -> None:
        with ui.element("div").classes("api-row"):
            ui.element("span").classes("api-dot on" if row.configured else "api-dot off")
            ui.label(row.display_name).classes("api-name")
            ui.label(row.state).classes("api-state")
            ui.label(row.env_hint).classes("api-env")
            result_lbl = ui.label("").classes("api-result")
            btn = ui.button("Test Connection").props("outline dense")
            btn.on_click(lambda _e=None, name=row.name, label=result_lbl, button=btn: self._test(name, label, button))

    def _test(self, provider: str, result_lbl: Any, btn: Any) -> None:
        btn.disable()
        result_lbl.text = "Testing..."
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
                result_lbl.text = f"ok  ({result.latency_ms:.0f} ms)"
                result_lbl.classes(add="ok")
            else:
                result_lbl.text = result.message
                result_lbl.classes(add="fail")
            btn.enable()

        timer = ui.timer(0.15, poll)

    def _assignment_section(self) -> None:
        registry = self.service.registry
        ui.label("Assignments").classes("text-h6 mt-8")
        ui.label("Default 用于未覆盖的 Agent。下拉显示名称，保存 catalog profile ID。").classes("muted")

        default_id = registry.default_model
        default_options = dict(build_model_options(registry))
        if default_id and default_id not in default_options:
            default_options = {default_id: profile_label(registry, default_id), **default_options}

        self.default_sel = (
            ui.select(default_options, value=default_id or None, label="Default")
            .props("outlined dense emit-value map-options")
            .classes("w-80")
            .on_value_change(lambda e: self._apply_default(e.value))
        )

        ui.label("Overrides").classes("text-subtitle2 mt-4")
        with ui.row().classes("w-full text-caption muted"):
            ui.label("Agent").classes("w-28")
            ui.label("Provider").classes("w-24")
            ui.label("Model").classes("flex-1")
        for role, label in ROLE_LABELS.items():
            profile_id = role_assigned_profile(registry, role)
            inherited = role_inherits_default(registry, role)
            try:
                provider = registry.get_model(profile_id).provider if profile_id else ""
            except KeyError:
                provider = ""
            with ui.row().classes("w-full items-center no-wrap"):
                ui.label(label).classes("w-28")
                ui.label(provider or "—").classes("w-24 muted")
                options = build_role_options(registry, role)
                value = INHERIT_VALUE if inherited else profile_id
                select = (
                    ui.select(options, value=value)
                    .props("outlined dense emit-value map-options")
                    .classes("flex-1")
                    .on_value_change(self._role_handler(role))
                )
                self.role_widgets[role] = select

        with ui.expansion("Advanced", icon="tune").classes("w-full mt-3"):
            ui.label("base_url、密钥环境变量名、超时。不含 SDK 与 HTTP 参数，也不含密钥值。").classes("muted")
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
            select.options = build_role_options(registry, role)
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


def _advanced_md(info: ProfileAdvanced) -> str:
    key = "not required" if not info.api_key_env else ("set" if info.key_configured else "missing")
    lines = [
        f"**{info.display_name}** `{info.profile_id}`",
        "",
        f"- Agent-facing provider: `{info.provider}`",
        f"- Model: `{info.model}`",
        f"- temperature: `{info.temperature}`",
        f"- timeout_sec: `{info.timeout_sec}`",
        f"- max_tokens: `{info.max_tokens}`",
        f"- max_retries: `{info.max_retries}`",
        f"- api_key_env: `{info.api_key_env or '—'}` ({key})",
        f"- base_url: `{info.base_url or '—'}`",
    ]
    return "\n".join(lines)
