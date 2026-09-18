"""Unified visual system and application chrome for the NiceGUI client."""

from __future__ import annotations

from nicegui import ui

NAV_GROUPS: tuple[tuple[str, tuple[tuple[str, str, str, str], ...]], ...] = (
    ("工作区", (("dashboard", "首页", "/", "space_dashboard"), ("studio", "创作工作台", "/studio", "edit_note"), ("outline", "章节大纲", "/outline", "account_tree"))),
    ("资料库", (("bible", "世界设定", "/bible", "public"), ("framework", "框架导入", "/framework", "upload_file"), ("memory", "创作记忆", "/memory", "memory"))),
    ("系统", (("models", "AI 模型", "/models", "smart_toy"), ("logs", "运行记录", "/logs", "receipt_long"), ("settings", "系统设置", "/settings", "settings"))),
)

SHARED_CSS = r"""
:root {
  --bg:#0d1117; --surface:#151b23; --surface-2:#1b222c; --surface-hover:#202936;
  --border:#2a3441; --border-soft:#222b36; --text:#f0f3f6; --text-2:#b5bec9; --muted:#84909f;
  --primary:#4b8df8; --primary-soft:rgba(75,141,248,.13); --success:#49a876; --warning:#d59b43; --danger:#d96b72;
  --radius:10px; --sidebar:224px; --topbar:64px;
  --font-ui:"Segoe UI","Microsoft YaHei UI","Microsoft YaHei","PingFang SC","Noto Sans CJK SC",sans-serif;
  --font-mono:Consolas,"JetBrains Mono","SFMono-Regular",monospace;
}
body.body--light{--bg:#f4f6f8;--surface:#ffffff;--surface-2:#f7f9fb;--surface-hover:#edf1f5;--border:#d6dde5;--border-soft:#e4e9ef;--text:#17202b;--text-2:#465363;--muted:#718092;--primary-soft:rgba(37,99,235,.09)}
body.body--light .workspace-sidebar{background:#f8fafc}body.body--light .workspace-topbar{background:rgba(255,255,255,.94)}
body.body--light .stat-card:hover,body.body--light .info-card:hover{background:#fbfcfd;border-color:#cbd5e1}
body.body--light .empty-state{background:#fafbfc}
html,body,#app{height:100%} body{margin:0;background:var(--bg);color:var(--text);font-family:var(--font-ui)}
body:has(.page-shell),body:has(.studio-shell){overflow:hidden}.nicegui-content,.q-page,.q-page-container{padding:0!important;min-height:0}
.q-btn,.q-field,.q-menu,.q-item{font-family:var(--font-ui)}.q-btn{min-height:36px;border-radius:8px;letter-spacing:0;transition:all .18s ease}
.q-btn:focus-visible,.q-field--focused{outline:2px solid rgba(75,141,248,.35);outline-offset:2px}
.q-field--outlined .q-field__control{border-radius:8px;background:rgba(255,255,255,.015)}
.q-field--outlined .q-field__control:before{border-color:var(--border)}.q-field--outlined:hover .q-field__control:before{border-color:#465365}
.q-tab{text-transform:none}.mono{font-family:var(--font-mono);font-variant-numeric:tabular-nums}.muted{color:var(--muted);font-size:13px;line-height:1.65}
.page-shell,.models-shell,.studio-shell{position:fixed;inset:0;overflow:hidden;background:var(--bg);color:var(--text)}
.workspace-sidebar{position:fixed;z-index:30;inset:0 auto 0 0;width:var(--sidebar);padding:18px 12px 14px;display:flex;flex-direction:column;background:#10151c;border-right:1px solid var(--border-soft)}
.brand-block{display:flex;align-items:center;gap:10px;height:38px;padding:0 8px 18px;box-sizing:content-box}.brand-mark{width:32px;height:32px;display:grid;place-items:center;border-radius:9px;background:var(--primary);color:white;font-weight:700;font-size:14px;box-shadow:0 5px 18px rgba(33,91,180,.22)}
.brand-name{font-size:14px;font-weight:650;color:var(--text);line-height:1.25}.brand-meta{font-size:11px;color:var(--muted);margin-top:2px}.nav-group-label{padding:14px 10px 6px;color:#657283;font-size:11px;font-weight:600;letter-spacing:.08em}
.nav-link{min-height:38px;display:flex;align-items:center;gap:10px;color:var(--text-2);font-size:13px;text-decoration:none;padding:0 10px;border-radius:8px;transition:background .18s ease,color .18s ease}
.nav-link:hover{color:var(--text);background:var(--surface-hover)}.nav-link.active{color:#eaf2ff;background:var(--primary-soft);box-shadow:inset 2px 0 var(--primary)}.nav-link .q-icon{color:#7f8c9e}.nav-link.active .q-icon{color:#73a9ff}
.sidebar-foot{margin-top:auto;padding:12px 10px 2px;border-top:1px solid var(--border-soft)}.service-line{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:12px}.status-dot{width:7px;height:7px;border-radius:50%;background:var(--success);box-shadow:0 0 0 3px rgba(73,168,118,.1)}
.workspace-topbar{position:fixed;z-index:20;left:var(--sidebar);right:0;top:0;height:var(--topbar);display:flex;align-items:center;gap:14px;padding:0 24px;background:rgba(13,17,23,.94);border-bottom:1px solid var(--border-soft);backdrop-filter:blur(10px)}
.topbar-title{min-width:0}.topbar-title h1{margin:0;font-size:16px;font-weight:650;color:var(--text)}.topbar-breadcrumb{color:var(--muted);font-size:11px;margin-top:2px}.topbar-chip{display:inline-flex;align-items:center;gap:7px;padding:6px 9px;border:1px solid var(--border);border-radius:7px;color:var(--text-2);font-size:12px;background:var(--surface)}.topbar-icon{color:var(--muted)}
.page-body,.models-body{position:absolute;inset:var(--topbar) 0 0 var(--sidebar);overflow:auto;padding:26px 30px 56px}.content-frame{width:min(1180px,100%);margin:0 auto}
.page-heading{display:flex;align-items:flex-start;gap:20px;margin-bottom:22px}.page-heading-copy{flex:1;min-width:0}.page-heading h2{margin:0;color:var(--text);font-size:22px;font-weight:650;line-height:1.35}.page-heading p{margin:6px 0 0;color:var(--muted);font-size:13px;line-height:1.6}.page-actions{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end}
.section-head{display:flex;align-items:center;gap:12px;margin:28px 0 12px}.section-head h3{margin:0;color:var(--text);font-size:14px;font-weight:600}.section-head p{margin:0;color:var(--muted);font-size:12px}.section-head:after{content:"";flex:1;height:1px;background:var(--border-soft)}
.stat-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:0 0 18px}.stat-card,.info-card,.panel-card{background:var(--surface);border:1px solid var(--border-soft);border-radius:var(--radius);transition:border-color .18s ease,background .18s ease,transform .18s ease}
.stat-card{min-height:112px;padding:16px}.stat-card:hover,.info-card:hover{border-color:#344152;background:#171e27}.stat-top{display:flex;align-items:center;justify-content:space-between;gap:8px}.stat-icon{width:30px;height:30px;display:grid;place-items:center;border-radius:8px;color:#78aaff;background:var(--primary-soft)}.stat-card .value{margin-top:15px;font:650 22px/1.1 var(--font-ui);color:var(--text)}.stat-card .label{margin-top:6px;font-size:12px;color:var(--muted)}
.card-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.info-card,.panel-card{padding:17px 18px}.info-card h3,.panel-title{font-size:13px;font-weight:600;color:var(--text);margin:0 0 12px}.info-card .q-markdown,.info-card p{color:var(--text-2)}.card-link{display:inline-flex;align-items:center;margin-top:12px;color:#79aaf8;font-size:12px;text-decoration:none}.card-link:hover{color:#a7c8ff}
.split{display:grid;grid-template-columns:minmax(170px,220px) minmax(0,1fr);gap:18px;min-height:460px}.split-wide{display:grid;grid-template-columns:minmax(220px,300px) minmax(0,1fr);gap:18px;min-height:460px}.side-list{border-right:1px solid var(--border-soft);padding-right:10px}.side-item{display:flex;width:100%;min-height:38px;justify-content:flex-start;text-align:left;padding:8px 10px;border-radius:7px;color:var(--text-2);font-size:13px;cursor:pointer}.side-item:hover{background:var(--surface-hover);color:var(--text)}.side-item.active{background:var(--primary-soft);color:#dbe9ff}
.status-badge{display:inline-flex;align-items:center;width:fit-content;padding:3px 8px;border-radius:999px;font-size:11px;font-weight:550;border:1px solid var(--border);color:var(--muted);background:rgba(255,255,255,.025)}.status-badge.success{color:#7ed3a3;border-color:rgba(73,168,118,.32);background:rgba(73,168,118,.09)}.status-badge.warning{color:#e5b66d;border-color:rgba(213,155,67,.32);background:rgba(213,155,67,.09)}.status-badge.danger{color:#ee9298;border-color:rgba(217,107,114,.32);background:rgba(217,107,114,.09)}.status-badge.info{color:#91b9fb;border-color:rgba(75,141,248,.32);background:var(--primary-soft)}
.empty-state{min-height:300px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:42px 24px;border:1px dashed var(--border);border-radius:var(--radius);background:rgba(21,27,35,.45)}.empty-icon{width:48px;height:48px;display:grid;place-items:center;border-radius:12px;color:#7caaf5;background:var(--primary-soft)}.empty-state h3{font-size:16px;margin:14px 0 5px}.empty-state p{max-width:420px;color:var(--muted);font-size:13px;line-height:1.65;margin:0 0 16px}
.inspect-block h1{font-size:21px}.inspect-block h2{font-size:16px}.inspect-block h3{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:18px 0 7px}.inspect-block p,.inspect-block li{font-size:13px;line-height:1.72;color:var(--text-2)}.inspect-block code{font-family:var(--font-mono);color:#a9c9ff}
.api-row{display:grid;grid-template-columns:20px 150px 90px minmax(180px,1fr) minmax(130px,auto) auto;align-items:center;gap:12px;width:100%;padding:12px 0;border-bottom:1px solid var(--border-soft)}.api-dot{width:8px;height:8px;border-radius:50%}.api-dot.on{background:var(--success)}.api-dot.off{background:#586474}.api-name{font-size:13px;color:var(--text)}.api-state{font-size:12px;color:var(--muted)}.api-env{min-width:0;font:11px var(--font-mono);color:var(--muted);overflow-wrap:anywhere}.api-result{font:11px var(--font-mono);text-align:right;color:var(--muted)}.api-result.ok{color:#7ed3a3}.api-result.fail{color:#ee9298}.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
@media(max-width:1050px){:root{--sidebar:76px}.brand-copy,.nav-text,.nav-group-label,.sidebar-foot{display:none}.brand-block{justify-content:center;padding-inline:0}.nav-link{justify-content:center;padding:0}.stat-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.api-row{grid-template-columns:18px 120px 80px 1fr auto}.api-result{display:none}}
@media(max-width:720px){:root{--sidebar:60px;--topbar:58px}.workspace-sidebar{width:60px;padding:14px 8px 10px}.brand-mark{width:28px;height:28px}.workspace-topbar{padding:0 16px}.topbar-chip{display:none}.page-body,.models-body{padding:20px 16px 42px}.stat-grid,.card-grid,.form-grid{grid-template-columns:1fr}.split,.split-wide{grid-template-columns:1fr}.side-list{border-right:0;border-bottom:1px solid var(--border-soft);padding:0 0 10px}.page-heading{flex-direction:column}.page-actions{justify-content:flex-start}.api-row{grid-template-columns:18px 1fr auto}.api-state,.api-env{display:none}}
"""


def apply_theme():
    ui.add_css(SHARED_CSS)
    ui.colors(primary="#4b8df8", positive="#49a876", warning="#d59b43", negative="#d96b72")
    dark = ui.dark_mode()
    dark.enable()
    return dark


def nav_links(active: str) -> None:
    for group, items in NAV_GROUPS:
        ui.label(group).classes("nav-group-label")
        for key, label, href, icon in items:
            cls = "nav-link active" if active == key else "nav-link"
            with ui.link(target=href).classes(cls).props(f'aria-label="{label}"'):
                ui.icon(icon, size="18px")
                ui.label(label).classes("nav-text")


def page_header(title: str, active: str, *, project: str = "AI 小说工厂") -> None:
    dark = apply_theme()
    with ui.element("aside").classes("workspace-sidebar"):
        with ui.element("div").classes("brand-block"):
            ui.label("NF").classes("brand-mark")
            with ui.element("div").classes("brand-copy"):
                ui.label("Story Factory").classes("brand-name")
                ui.label("AI 小说创作工作台").classes("brand-meta")
        nav_links(active)
        with ui.element("div").classes("sidebar-foot"):
            with ui.element("div").classes("service-line"):
                ui.element("span").classes("status-dot")
                ui.label("本地服务运行正常")
    with ui.element("header").classes("workspace-topbar"):
        with ui.element("div").classes("topbar-title"):
            ui.label(title).style("font-size:16px;font-weight:650;color:var(--text)")
            ui.label(f"{project} / {title}").classes("topbar-breadcrumb")
        ui.space()
        with ui.element("div").classes("topbar-chip"):
            ui.element("span").classes("status-dot")
            ui.label("服务正常")
        ui.button(icon="contrast", on_click=dark.toggle).props("flat round dense aria-label=切换主题").classes("topbar-icon").tooltip("切换深色 / 浅色主题")


def empty_book() -> None:
    from factory.gui.components import empty_state
    with ui.element("div").classes("page-body"):
        with ui.element("div").classes("content-frame"):
            empty_state("暂无小说项目", "创建第一个项目并生成基础架构后，即可开始规划章节和创作正文。", icon="library_add", action_label="查看创建命令", on_action=lambda: ui.notify("在终端运行：factory init <项目名> && factory architect", type="info"))
