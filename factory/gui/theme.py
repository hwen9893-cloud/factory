"""Shared chrome. Pages talk to FactoryService only."""

from __future__ import annotations

from nicegui import ui

NAV_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("dashboard", "Dashboard", "/"),
    ("studio", "Chapter Studio", "/studio"),
    ("bible", "Story Bible", "/bible"),
    ("outline", "Outline", "/outline"),
    ("memory", "Memory", "/memory"),
    ("models", "Models", "/models"),
    ("settings", "Settings", "/settings"),
)

SHARED_CSS = """
html, body, #app { height: 100%; }
body:has(.studio-shell) { overflow: hidden; }
.nicegui-content, .q-page, .q-page-container { padding: 0 !important; min-height: 0; }
body:has(.studio-shell) .nicegui-content,
body:has(.studio-shell) .q-page,
body:has(.studio-shell) .q-page-container { height: 100% !important; }
.studio-header { flex: 0 0 auto; display: flex; align-items: center; gap: 12px; padding: 8px 16px;
  border-bottom: 1px solid #2a2e36; background: #16181d; }
.studio-brand { font-size: 13px; letter-spacing: 0.08em; text-transform: uppercase; color: #8b909a; min-width: 140px; }
.studio-brand strong { display: block; color: #f2f0ec; font-size: 15px; letter-spacing: 0; text-transform: none; }
.nav-link { color: #9aa0aa; font-size: 13px; text-decoration: none; padding: 4px 8px; border-radius: 6px; }
.nav-link:hover { color: #f2f0ec; background: #1e222a; }
.nav-link.active { color: #f2f0ec; background: #2a3344; }
.muted { color: #8b909a; font-size: 13px; }
.inspect-block h3 { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: #8b909a; margin: 12px 0 6px; }
.inspect-block p, .inspect-block li { font-size: 13px; line-height: 1.55; color: #d7d4ce; }
.page-shell, .models-shell { position: fixed; inset: 0; display: flex; flex-direction: column;
  overflow: hidden; background: #101216; color: #e8e6e3; }
.page-body, .models-body { flex: 1; min-height: 0; overflow: auto; max-width: 960px;
  width: 100%; margin: 0 auto; padding: 24px 20px 56px; }
.stat-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 16px 0 20px; }
.stat-card, .info-card { background: #16181d; border: 1px solid #2a2e36; border-radius: 8px; padding: 14px 16px; }
.stat-card .value { font-size: 18px; color: #f2f0ec; }
.stat-card .label { font-size: 12px; color: #8b909a; margin-top: 4px; }
.card-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.info-card h3 { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: #8b909a; margin: 0 0 8px; }
.split { display: grid; grid-template-columns: 200px 1fr; gap: 16px; min-height: 420px; }
.split-wide { display: grid; grid-template-columns: 280px 1fr; gap: 16px; min-height: 420px; }
.side-list { border-right: 1px solid #2a2e36; padding-right: 8px; }
.side-item { display: block; width: 100%; text-align: left; padding: 8px 10px; border-radius: 6px;
  color: #d7d4ce; font-size: 13px; cursor: pointer; }
.side-item:hover { background: #1e222a; }
.side-item.active { background: #2a3344; color: #fff; }
.api-row { display: flex; align-items: center; gap: 12px; width: 100%; padding: 10px 0;
  border-bottom: 1px solid #2a2e36; }
.api-dot { width: 10px; height: 10px; border-radius: 50%; flex: 0 0 auto; }
.api-dot.on { background: #6fbf8b; }
.api-dot.off { background: transparent; border: 2px solid #8b909a; }
.api-name { width: 160px; font-size: 14px; }
.api-state { width: 110px; font-size: 13px; }
.api-env { flex: 1; font-size: 12px; color: #8b909a; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.api-result { min-width: 180px; font-size: 12px; text-align: right; }
.api-result.ok { color: #6fbf8b; }
.api-result.fail { color: #d07070; }
"""


def apply_theme() -> None:
    ui.add_css(SHARED_CSS)
    ui.dark_mode().enable()


def nav_links(active: str) -> None:
    for key, label, href in NAV_ITEMS:
        cls = "nav-link active" if active == key else "nav-link"
        ui.link(label, href).classes(cls)


def page_header(title: str, active: str) -> None:
    apply_theme()
    with ui.element("div").classes("studio-header"):
        with ui.element("div").classes("studio-brand"):
            ui.html(f"<strong>{title}</strong>Novel Factory")
        nav_links(active)


def empty_book() -> None:
    with ui.column().classes("p-8"):
        ui.label("还没有书。先运行：factory init <name> && factory architect")
