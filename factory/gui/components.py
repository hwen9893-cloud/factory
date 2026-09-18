"""Small reusable presentational components shared by GUI pages."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui


def page_intro(title: str, description: str) -> Any:
    with ui.element("div").classes("page-heading") as root:
        with ui.element("div").classes("page-heading-copy"):
            ui.html(f"<h2>{title}</h2><p>{description}</p>")
    return root


def section_header(title: str, description: str = "") -> None:
    with ui.element("div").classes("section-head"):
        ui.html(f"<h3>{title}</h3>")
        if description:
            ui.label(description)


def metric_card(value: str, label: str, *, icon: str = "analytics", hint: str = "") -> None:
    with ui.element("div").classes("stat-card"):
        with ui.element("div").classes("stat-top"):
            ui.label(label).classes("muted")
            with ui.element("span").classes("stat-icon"):
                ui.icon(icon, size="17px")
        ui.label(value).classes("value")
        if hint:
            ui.label(hint).classes("label")


def status_badge(text: str, tone: str = "neutral") -> Any:
    return ui.label(text).classes(f"status-badge {tone}")


def empty_state(title: str, description: str, *, icon: str = "inbox", action_label: str | None = None, on_action: Callable[[], Any] | None = None) -> None:
    with ui.element("div").classes("empty-state"):
        with ui.element("span").classes("empty-icon"):
            ui.icon(icon, size="24px")
        ui.html(f"<h3>{title}</h3><p>{description}</p>")
        if action_label and on_action:
            ui.button(action_label, on_click=on_action, icon="add").props("unelevated no-caps")


def friendly_error(message: str) -> tuple[str, str]:
    raw = str(message or "未知错误")
    lowered = raw.lower()
    if any(token in lowered for token in ("connection refused", "errno 61", "connecterror")):
        return "无法连接到模型服务", "请确认模型服务已启动，且地址、端口与网络连接均正确。\n\n技术详情：" + raw
    if any(token in lowered for token in ("api key", "unauthorized", "401")):
        return "模型服务认证失败", "请检查对应环境变量是否已配置，然后重启工作台。\n\n技术详情：" + raw
    if "timeout" in lowered or "timed out" in lowered:
        return "模型响应超时", "模型可能正忙或网络不稳定，请稍后重试。\n\n技术详情：" + raw
    return "任务执行失败", "请稍后重试；如问题持续，可在运行记录中查看技术详情。\n\n技术详情：" + raw


def notify_error(message: str) -> None:
    summary, detail = friendly_error(message)
    ui.notify(summary, type="negative", caption=detail.split("\n\n", 1)[0], timeout=7000)
