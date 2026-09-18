"""Chapter Studio — the core operations page. Talks only to FactoryService."""

from __future__ import annotations

from queue import Empty, Queue
from threading import Thread
from time import monotonic
from typing import Any, Callable

from nicegui import ui

from factory.events import WorkflowEvent
from factory.gui.adapters import inspector_view, nav_tree
from factory.gui.components import notify_error, status_badge
from factory.gui.presentation.model_options import build_model_options, profile_label
from factory.gui.presentation.inspector import (
    chapter_version_label,
    context_md,
    continuity_md,
    memory_md,
    plan_md,
    review_md,
)
from factory.gui.presentation.nav import NavNode
from factory.gui.presentation.progress import (
    TRACK_STEPS,
    is_error,
    is_stage_done,
    is_stage_start,
    is_token,
    is_workflow_done,
    is_workflow_start,
    status_text,
    step_class,
    step_label,
    step_mark,
    track_done_stage,
    track_key,
)
from factory.gui.theme import apply_theme, empty_book, page_header
from factory.service import ChapterResult, FactoryService
from factory.settings import Settings

_CSS = """
.studio-body { position:absolute; inset:var(--topbar) 0 0 var(--sidebar); min-height:0; display:flex; }
.studio-nav { width:250px; flex:0 0 250px; border-right:1px solid var(--border-soft); overflow:auto; padding:18px 12px; background:#11171f; }
.studio-editor { flex:1; min-width:0; min-height:0; display:flex; flex-direction:column; padding:14px 20px 12px; }
.studio-inspect { width:350px; flex:0 0 350px; min-height:0; border-left:1px solid var(--border-soft); overflow:auto; padding:10px 12px 18px; background:#11171f; }
.studio-inspect .q-tab { min-height: 36px; padding: 0 10px; font-size: 12px; }
.studio-toolbar { display:flex; align-items:center; flex-wrap:wrap; gap:8px; padding-bottom:12px; border-bottom:1px solid var(--border-soft); }
.studio-actions { margin-left:auto; display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
.studio-runline { display:flex; align-items:center; gap:10px; min-height:32px; padding:8px 0 2px; }
.studio-status { font-size:12px; color:var(--text-2); }
.elapsed { margin-left:auto; font:11px var(--font-mono); color:var(--muted); }
.nav-book { font-size:14px; font-weight:650; margin:0 5px 12px; }
.nav-vol { font-size:11px; color:var(--muted); margin:16px 8px 5px; }
.nav-ch { display: flex; align-items: center; gap: 8px; width: 100%; padding: 6px 8px; border-radius: 6px;
  cursor: pointer; font-size: 13px; color: var(--text-2); transition:background .18s ease; }
.nav-ch:hover { background: var(--surface-hover); }.nav-ch.active { background:var(--primary-soft); color:#eaf2ff; }
.nav-status { margin-left:auto; font-size:10px; color:var(--muted); }.nav-status.final { color:#7ed3a3; }.nav-status.draft { color:#e5b66d; }.nav-status.failed { color:#ee9298; }.nav-status.running { color:#91b9fb; }
.editor-title { flex: 0 0 auto; }
.editor-meta { flex:0 0 auto; display:flex; align-items:center; gap:14px; font-size:12px; color:var(--muted); padding:4px 0 8px; }
.studio-steps { flex: 0 0 auto; display: flex; flex-wrap: wrap; gap: 6px 14px; padding: 0 0 8px; font-size: 12px; }
.step-pending { color:var(--muted); }.step-active { color:#91b9fb; }.step-done { color:#7ed3a3; }
.body-wrap { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; }
.body-wrap .q-textarea, .body-wrap .q-field, .body-wrap .q-field__inner, .body-wrap .q-field__control { height: 100%; }
.body-wrap .q-field__control { background:var(--surface)!important; border-radius:9px!important; }
.body-wrap textarea { height: 100% !important; font-size: 16px !important; line-height: 1.85 !important;
  font-family:"Songti SC","Noto Serif CJK SC","Microsoft YaHei",serif!important; padding:18px!important; }
@media(max-width:1050px){.studio-nav{width:210px;flex-basis:210px}.studio-inspect{width:300px;flex-basis:300px}.studio-editor{padding-inline:14px}}
@media(max-width:820px){.studio-inspect{display:none}.studio-nav{width:190px;flex-basis:190px}}
@media(max-width:600px){.studio-nav{display:none}.studio-editor{padding:10px}.studio-toolbar .q-select,.studio-toolbar .q-field{max-width:150px}.studio-actions{margin-left:0}}
body.body--light .studio-nav,body.body--light .studio-inspect{background:#f8fafc}
"""

_STEP_ZH = {"context": "准备上下文", "plan": "章节规划", "write": "生成正文", "continuity": "一致性检查", "review": "质量审阅", "memory": "更新记忆"}
_STATUS_ZH = {"Planning": "正在规划章节", "Writing": "正在生成正文", "Checking continuity": "正在检查一致性", "Reviewing": "正在审阅质量", "Revising": "正在润色修改", "Updating memory": "正在更新记忆", "Saving": "正在保存", "Planning volume": "正在规划分卷"}
_CH_STATUS_ZH = {"final": "已定稿", "draft": "草稿", "failed": "失败", "running": "运行中", "outlined": "待创作"}


def build_studio(*, book_id: str | None, settings: Settings) -> None:
    apply_theme()
    ui.add_css(_CSS)
    StudioPage(settings, book_id).render()


class StudioPage:
    def __init__(self, settings: Settings, book_id: str | None) -> None:
        self.events: Queue[WorkflowEvent | tuple[str, str | None]] = Queue()
        self.service = FactoryService(settings, on_progress=self.events.put)
        self.book_id = self.service.resolve_book(book_id)
        self.ch_no = 1
        self.volume_no = 1
        self.busy = False
        self.title_in: Any = None
        self.body_in: Any = None
        self.words_lbl: Any = None
        self.version_lbl: Any = None
        self.status_lbl: Any = None
        self.model_sel: Any = None
        self.target_in: Any = None
        self.nav_box: Any = None
        self.inspect: dict[str, Any] = {}
        self.buttons: list[Any] = []
        self.steps: dict[str, Any] = {}
        self._stream_buf = ""
        self._stream_active = False
        self.started_at: float | None = None
        self.elapsed_lbl: Any = None
        self.inspect_panel: Any = None
        self.inspect_visible = True

    def render(self) -> None:
        if not self.book_id:
            page_header("创作工作台", "studio")
            empty_book()
            return
        self._focus_current_chapter()
        view = self.service.load_chapter(self.book_id, self.ch_no)
        models = dict(build_model_options(self.service.registry, agent="chapter_writer"))
        assigned = self.service.registry.assigned_model_name("chapter_writer", default="writer")
        if assigned not in models:
            models = {assigned: profile_label(self.service.registry, assigned), **models}

        with ui.element("div").classes("studio-shell"):
            page_header("创作工作台", "studio", project=str(self.book_id))
            with ui.element("div").classes("studio-body"):
                self.nav_box = ui.element("div").classes("studio-nav")
                with ui.element("div").classes("studio-editor"):
                    with ui.element("div").classes("studio-toolbar"):
                        # Writer Model remains a registry-backed profile selector; the visible label is localized.
                        self.model_sel = (
                            ui.select(models, value=assigned, label="创作模型")
                            .props("dense outlined emit-value map-options options-dense")
                            .classes("w-52")
                            .on_value_change(self._on_writer_model)
                        )
                        self.target_in = (
                            ui.number(label="目标字数", value=self.service.settings.chapter_target_words, format="%.0f")
                            .props("dense outlined suffix=字")
                            .classes("w-32")
                        )
                        with ui.element("div").classes("studio-actions"):
                            self._action("规划", self._plan, primary=False, icon="schema")
                            self._action("生成正文", self._generate, primary=True, icon="auto_awesome")
                            self._action("审阅", self._review, primary=False, icon="fact_check")
                            self._action("润色", self._revise, primary=False, icon="auto_fix_high")
                            self._action("定稿", self._accept, primary=False, icon="check_circle")
                            ui.button(icon="dock_to_right", on_click=self._toggle_inspector).props("flat round dense aria-label=收起资料面板").tooltip("展开 / 收起资料面板")
                    with ui.element("div").classes("studio-runline"):
                        status_badge("就绪", "success")
                        self.status_lbl = ui.label("准备就绪，可开始规划或生成正文").classes("studio-status")
                        self.elapsed_lbl = ui.label("00:00").classes("elapsed")
                    self.title_in = ui.input(value=view.title, placeholder="输入章节标题").props("borderless").classes("text-h6 w-full editor-title")
                    with ui.element("div").classes("editor-meta"):
                        self.words_lbl = ui.label(f"{view.word_count} 字")
                        self.version_lbl = ui.label(self._version_label(view))
                        ui.space()
                        save_btn = ui.button("保存修改", on_click=self._save, icon="save").props("flat dense no-caps")
                        cont_btn = ui.button("继续生成", on_click=self._continue, icon="add").props("flat dense no-caps")
                        self.buttons.extend([save_btn, cont_btn])
                    self._render_steps()
                    with ui.element("div").classes("body-wrap"):
                        self.body_in = ui.textarea(value=view.body, placeholder="在这里开始创作…").props("outlined input-class=h-full").classes("w-full h-full")
                    self.body_in.on("update:model-value", lambda e: self._count_words())
                with ui.element("div").classes("studio-inspect") as self.inspect_panel:
                    self._inspector_tabs()
        self._paint_nav()
        self._paint_inspector()
        ui.timer(0.2, self._drain)

    def _on_writer_model(self, e: Any) -> None:
        profile_id = str(getattr(e, "value", e) or "")
        if not profile_id or profile_id == self.service.registry.assigned_model_name(
            "chapter_writer", default="writer"
        ):
            return
        self.service.set_role_model("writer", profile_id, persist=True)

    def _action(self, label: str, handler: Callable[[], None], *, primary: bool, icon: str = "") -> None:
        props = "unelevated" if primary else "outline"
        btn = ui.button(label, on_click=handler, icon=icon or None).props(f"{props} no-caps dense")
        self.buttons.append(btn)

    def _inspector_tabs(self) -> None:
        with ui.tabs().classes("w-full") as tabs:
            tab_plan = ui.tab("规划")
            tab_ctx = ui.tab("上下文")
            tab_rev = ui.tab("审阅")
            tab_con = ui.tab("一致性")
            tab_mem = ui.tab("记忆")
        with ui.tab_panels(tabs, value=tab_plan).classes("w-full"):
            with ui.tab_panel(tab_plan):
                self.inspect["plan"] = ui.markdown("").classes("inspect-block")
            with ui.tab_panel(tab_ctx):
                self.inspect["context"] = ui.markdown("").classes("inspect-block")
            with ui.tab_panel(tab_rev):
                self.inspect["review"] = ui.markdown("").classes("inspect-block")
            with ui.tab_panel(tab_con):
                self.inspect["continuity"] = ui.markdown("").classes("inspect-block")
            with ui.tab_panel(tab_mem):
                self.inspect["memory"] = ui.markdown("").classes("inspect-block")

    def _paint_nav(self) -> None:
        assert self.book_id and self.nav_box
        self.nav_box.clear()
        tree = nav_tree(self.service, self.book_id)
        with self.nav_box:
            ui.label(tree.label).classes("nav-book")
            for volume in tree.children:
                title = volume.label.split("  ", 1)[1] if "  " in volume.label else ""
                ui.label(f"第 {volume.volume_no or 1} 卷" + (f" · {title}" if title else "")).classes("nav-vol")
                for chapter in volume.children:
                    self._nav_chapter(chapter)
            ui.button("新建章节", on_click=self._new_chapter, icon="add").props("flat dense no-caps").classes("mt-3")

    def _nav_chapter(self, node: NavNode) -> None:
        ch_no = int(node.ch_no or 0)
        classes = "nav-ch active" if ch_no == self.ch_no else "nav-ch"

        def select(_e=None, number=ch_no, volume=node.volume_no) -> None:
            self._select_chapter(number, volume)

        with ui.element("div").classes(classes).on("click", select):
            title = node.label.split("  ", 1)[1] if "  " in node.label else ""
            ui.label(f"第 {ch_no} 章" + (f" · {title}" if title else ""))
            ui.label(_CH_STATUS_ZH.get(node.status, node.status)).classes(f"nav-status {node.status}")

    def _select_chapter(self, ch_no: int, volume_no: int | None) -> None:
        if self.busy:
            return
        self.ch_no = ch_no
        self.volume_no = int(volume_no or 1)
        self._reload_editor()
        self._paint_nav()
        self._paint_inspector()

    def _reload_editor(self) -> None:
        assert self.book_id
        view = self.service.load_chapter(self.book_id, self.ch_no)
        self.title_in.value = view.title
        self.body_in.value = view.body
        self._show_meta(view)

    def _show_meta(self, chapter: ChapterResult) -> None:
        self.words_lbl.text = f"{chapter.word_count} 字"
        self.version_lbl.text = self._version_label(chapter)

    def _version_label(self, chapter: ChapterResult) -> str:
        raw = chapter_version_label(chapter.source, chapter.revision, chapter.pipeline_status)
        for source, label in (("final", "定稿"), ("draft", "草稿"), ("completed", "已完成"), ("failed", "失败"), ("outlined", "已规划")):
            raw = raw.replace(source, label)
        return raw.replace("rev", "修订")

    def _toggle_inspector(self) -> None:
        if self.inspect_panel is None:
            return
        self.inspect_visible = not self.inspect_visible
        self.inspect_panel.set_visibility(self.inspect_visible)

    def _count_words(self) -> None:
        body = str(self.body_in.value or "")
        self.words_lbl.text = f"{len(body)} 字"

    def _paint_inspector(self) -> None:
        assert self.book_id
        data = inspector_view(self.service, self.book_id, self.ch_no)
        self.inspect["plan"].set_content(plan_md(data.plan))
        self.inspect["context"].set_content(context_md(data.context))
        self.inspect["review"].set_content(review_md(data.review))
        self.inspect["continuity"].set_content(continuity_md(data.continuity))
        self.inspect["memory"].set_content(memory_md(data.memory))

    def _editor_kwargs(self) -> dict[str, Any]:
        return {
            "title": str(self.title_in.value or ""),
            "body": str(self.body_in.value or ""),
            "model": self.model_sel.value,
            "target_words": int(self.target_in.value or self.service.settings.chapter_target_words),
        }

    def _focus_current_chapter(self) -> None:
        assert self.book_id
        tree = nav_tree(self.service, self.book_id)
        chapters = [chapter for volume in tree.children for chapter in volume.children]
        current = self.service.book_status(self.book_id).current_chapter
        if not chapters:
            self.ch_no = current or 1
            return
        match = next((item for item in chapters if item.ch_no == current), chapters[0])
        self.ch_no = int(match.ch_no or 1)
        self.volume_no = int(match.volume_no or 1)

    def _save(self) -> None:
        assert self.book_id
        view = self.service.save_chapter(
            self.book_id,
            self.ch_no,
            str(self.title_in.value or ""),
            str(self.body_in.value or ""),
        )
        self._show_meta(view)
        self.status_lbl.text = "修改已保存"
        self._paint_nav()

    def _new_chapter(self) -> None:
        assert self.book_id
        if self.busy:
            return
        self.ch_no = self.service.add_chapter(self.book_id, volume_no=self.volume_no)
        self._reload_editor()
        self._paint_nav()
        self._paint_inspector()
        self.status_lbl.text = f"已新建第 {self.ch_no} 章"

    def _plan(self) -> None:
        self._spawn("正在规划章节…", lambda: self.service.plan(self.book_id, self.ch_no, **self._editor_kwargs()))

    def _generate(self) -> None:
        self._spawn("正在生成正文…", lambda: self.service.generate(self.book_id, self.ch_no, **self._editor_kwargs()))

    def _review(self) -> None:
        self._spawn("正在审阅质量…", lambda: self.service.review(self.book_id, self.ch_no, **self._editor_kwargs()))

    def _revise(self) -> None:
        self._spawn("正在润色修改…", lambda: self.service.revise(self.book_id, self.ch_no, **self._editor_kwargs()))

    def _continue(self) -> None:
        self._spawn("正在继续生成…", lambda: self.service.continue_generate(self.book_id, self.ch_no, **self._editor_kwargs()))

    def _accept(self) -> None:
        self._spawn("正在定稿并更新记忆…", lambda: self.service.accept(self.book_id, self.ch_no, **self._editor_kwargs()))

    def _spawn(self, label: str, fn: Callable[[], Any]) -> None:
        if self.busy or not self.book_id:
            return
        self.busy = True
        self.started_at = monotonic()
        self.status_lbl.text = label
        for btn in self.buttons:
            btn.disable()

        def worker() -> None:
            try:
                fn()
                self.events.put(("done", None))
            except Exception as exc:  # noqa: BLE001 — surface any Core error in the status line
                self.events.put(("fail", str(exc)))

        Thread(target=worker, daemon=True).start()

    def _render_steps(self) -> None:
        with ui.element("div").classes("studio-steps"):
            for key, label, _stages in TRACK_STEPS:
                self.steps[key] = ui.label(f"{step_mark('pending')} {_STEP_ZH.get(key, label)}").classes(step_class("pending"))

    def _reset_steps(self) -> None:
        self._stream_buf = ""
        self._stream_active = False
        for key, label, _stages in TRACK_STEPS:
            widget = self.steps.get(key)
            if widget is None:
                continue
            widget.text = f"{step_mark('pending')} {_STEP_ZH.get(key, label)}"
            widget.classes(replace=step_class("pending"))

    def _set_step(self, key: str, state: str) -> None:
        widget = self.steps.get(key)
        if widget is None:
            return
        widget.text = f"{step_mark(state)} {_STEP_ZH.get(key, step_label(key))}"
        widget.classes(replace=step_class(state))

    def _apply_tokens(self, chunk: str) -> None:
        if not chunk or self.body_in is None:
            return
        if self._stream_active and not self._stream_buf:
            self.body_in.value = chunk
            self._stream_buf = chunk
        else:
            self._stream_buf += chunk
            self.body_in.value = self._stream_buf
        self.words_lbl.text = f"{len(str(self.body_in.value or ''))} 字"

    def _handle_workflow_event(self, item: WorkflowEvent) -> None:
        if is_workflow_start(item):
            self._reset_steps()
            return
        if is_token(item):
            self._apply_tokens(item.content)
            return
        if is_stage_start(item):
            raw = status_text(item)
            self.status_lbl.text = _STATUS_ZH.get(raw, raw)
        elif is_error(item):
            self.status_lbl.text = status_text(item)
        key = track_key(item.stage, item.agent)
        if key and is_stage_start(item):
            self._set_step(key, "active")
            if key == "write":
                self._stream_active = True
                self._stream_buf = ""
        elif key and is_stage_done(item):
            last = track_done_stage(key)
            if key == "context" and item.stage != last:
                self._set_step(key, "active")
            else:
                self._set_step(key, "done")
            if key == "write":
                self._stream_active = False
                if not self._stream_buf:
                    self._reload_editor()
        if is_workflow_done(item):
            self._stream_active = False

    def _drain(self) -> None:
        if self.started_at is not None and self.elapsed_lbl is not None:
            elapsed = int(monotonic() - self.started_at)
            self.elapsed_lbl.text = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
        pending: list[Any] = []
        while True:
            try:
                pending.append(self.events.get_nowait())
            except Empty:
                break
        tokens: list[str] = []

        def flush_tokens() -> None:
            if tokens:
                self._apply_tokens("".join(tokens))
                tokens.clear()

        for item in pending:
            if isinstance(item, WorkflowEvent) and is_token(item):
                tokens.append(item.content)
                continue
            flush_tokens()
            if isinstance(item, WorkflowEvent):
                self._handle_workflow_event(item)
                continue
            kind, message = item
            self.busy = False
            self._stream_active = False
            self.started_at = None
            for btn in self.buttons:
                btn.enable()
            if kind == "fail":
                self.status_lbl.text = "任务执行失败"
                notify_error(message or "未知错误")
            else:
                self.status_lbl.text = "任务已完成，内容已更新"
                self._reload_editor()
                self._paint_nav()
                self._paint_inspector()
        flush_tokens()
