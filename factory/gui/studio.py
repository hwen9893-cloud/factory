"""Chapter Studio — the core operations page. Talks only to FactoryService."""

from __future__ import annotations

from queue import Empty, Queue
from threading import Thread
from typing import Any, Callable

from nicegui import ui

from factory.events import WorkflowEvent
from factory.gui.adapters import inspector_view, nav_tree
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
from factory.gui.theme import apply_theme, empty_book, nav_links, page_header
from factory.service import ChapterResult, FactoryService
from factory.settings import Settings

_CSS = """
.studio-shell { position: fixed; inset: 0; display: flex; flex-direction: column; background: #101216; color: #e8e6e3; }
.studio-actions { margin-left: auto; display: flex; gap: 6px; align-items: center; }
.studio-status { font-size: 13px; color: #c9a227; min-width: 180px; text-align: right; }
.studio-body { flex: 1; min-height: 0; display: flex; }
.studio-nav { width: 240px; flex: 0 0 240px; border-right: 1px solid #2a2e36; overflow: auto; padding: 12px 10px; }
.studio-editor { flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column; padding: 12px 18px 10px; }
.studio-inspect { width: 360px; flex: 0 0 360px; min-height: 0; border-left: 1px solid #2a2e36; overflow: auto; padding: 8px 10px 16px; }
.studio-inspect .q-tab { min-height: 36px; padding: 0 10px; font-size: 12px; }
.nav-book { font-size: 15px; font-weight: 600; margin-bottom: 8px; }
.nav-vol { font-size: 12px; color: #9aa0aa; margin: 10px 0 4px; }
.nav-ch { display: flex; align-items: center; gap: 8px; width: 100%; padding: 6px 8px; border-radius: 6px;
  cursor: pointer; font-size: 13px; color: #d7d4ce; }
.nav-ch:hover { background: #1e222a; }
.nav-ch.active { background: #2a3344; color: #fff; }
.nav-status { margin-left: auto; font-size: 10px; letter-spacing: 0.04em; text-transform: uppercase; color: #8b909a; }
.nav-status.final { color: #6fbf8b; }
.nav-status.draft { color: #c9a227; }
.nav-status.failed { color: #d07070; }
.nav-status.running { color: #6ea8ff; }
.editor-title { flex: 0 0 auto; }
.editor-meta { flex: 0 0 auto; display: flex; align-items: center; gap: 16px; font-size: 12px; color: #8b909a; padding: 4px 0 8px; }
.studio-steps { flex: 0 0 auto; display: flex; flex-wrap: wrap; gap: 6px 14px; padding: 0 0 8px; font-size: 12px; }
.step-pending { color: #8b909a; }
.step-active { color: #c9a227; }
.step-done { color: #6fbf8b; }
.body-wrap { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; }
.body-wrap .q-textarea, .body-wrap .q-field, .body-wrap .q-field__inner, .body-wrap .q-field__control { height: 100%; }
.body-wrap .q-field__control { background: #1a1d24 !important; }
.body-wrap textarea { height: 100% !important; font-size: 16px !important; line-height: 1.85 !important;
  font-family: "Iowan Old Style", "Songti SC", "Noto Serif SC", Georgia, serif !important; }
"""


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

    def render(self) -> None:
        if not self.book_id:
            page_header("Chapter Studio", "studio")
            empty_book()
            return
        self._focus_current_chapter()
        view = self.service.load_chapter(self.book_id, self.ch_no)
        models = dict(build_model_options(self.service.registry, agent="chapter_writer"))
        assigned = self.service.registry.assigned_model_name("chapter_writer", default="writer")
        if assigned not in models:
            models = {assigned: profile_label(self.service.registry, assigned), **models}

        with ui.element("div").classes("studio-shell"):
            with ui.element("div").classes("studio-header"):
                with ui.element("div").classes("studio-brand"):
                    ui.html("<strong>Chapter Studio</strong>Novel Factory")
                nav_links("studio")
                self.model_sel = (
                    ui.select(models, value=assigned, label="Writer Model")
                    .props("dense outlined emit-value map-options")
                    .classes("w-56")
                    .on_value_change(self._on_writer_model)
                )
                self.target_in = (
                    ui.number(label="Target", value=self.service.settings.chapter_target_words, format="%.0f")
                    .props("dense outlined suffix=words")
                    .classes("w-36")
                )
                with ui.element("div").classes("studio-actions"):
                    self._action("Plan", self._plan, primary=False)
                    self._action("Generate", self._generate, primary=True)
                    self._action("Review", self._review, primary=False)
                    self._action("Revise", self._revise, primary=False)
                    self._action("Accept", self._accept, primary=False)
                self.status_lbl = ui.label("Ready").classes("studio-status")
            with ui.element("div").classes("studio-body"):
                self.nav_box = ui.element("div").classes("studio-nav")
                with ui.element("div").classes("studio-editor"):
                    self.title_in = ui.input(value=view.title).props("borderless").classes("text-h6 w-full editor-title")
                    with ui.element("div").classes("editor-meta"):
                        self.words_lbl = ui.label(f"{view.word_count} 字")
                        self.version_lbl = ui.label(
                            chapter_version_label(view.source, view.revision, view.pipeline_status)
                        )
                        ui.space()
                        save_btn = ui.button("Save", on_click=self._save).props("flat dense")
                        cont_btn = ui.button("继续生成", on_click=self._continue).props("flat dense")
                        self.buttons.extend([save_btn, cont_btn])
                    self._render_steps()
                    with ui.element("div").classes("body-wrap"):
                        self.body_in = (
                            ui.textarea(value=view.body)
                            .props("outlined input-class=h-full")
                            .classes("w-full h-full")
                        )
                    self.body_in.on("update:model-value", lambda e: self._count_words())
                with ui.element("div").classes("studio-inspect"):
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

    def _action(self, label: str, handler: Callable[[], None], *, primary: bool) -> None:
        props = "unelevated" if primary else "outline"
        btn = ui.button(label, on_click=handler).props(props)
        self.buttons.append(btn)

    def _inspector_tabs(self) -> None:
        with ui.tabs().classes("w-full") as tabs:
            tab_plan = ui.tab("Plan")
            tab_ctx = ui.tab("Context")
            tab_rev = ui.tab("Review")
            tab_con = ui.tab("Continuity")
            tab_mem = ui.tab("Memory")
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
                ui.label(volume.label).classes("nav-vol")
                for chapter in volume.children:
                    self._nav_chapter(chapter)
            ui.button("新建章节", on_click=self._new_chapter).props("flat dense").classes("mt-3")

    def _nav_chapter(self, node: NavNode) -> None:
        ch_no = int(node.ch_no or 0)
        classes = "nav-ch active" if ch_no == self.ch_no else "nav-ch"

        def select(_e=None, number=ch_no, volume=node.volume_no) -> None:
            self._select_chapter(number, volume)

        with ui.element("div").classes(classes).on("click", select):
            ui.label(node.label)
            ui.label(node.status).classes(f"nav-status {node.status}")

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
        self.version_lbl.text = chapter_version_label(chapter.source, chapter.revision, chapter.pipeline_status)

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
        self.status_lbl.text = "Saved"
        self._paint_nav()

    def _new_chapter(self) -> None:
        assert self.book_id
        if self.busy:
            return
        self.ch_no = self.service.add_chapter(self.book_id, volume_no=self.volume_no)
        self._reload_editor()
        self._paint_nav()
        self._paint_inspector()
        self.status_lbl.text = f"Chapter {self.ch_no}"

    def _plan(self) -> None:
        self._spawn("Planning...", lambda: self.service.plan(self.book_id, self.ch_no, **self._editor_kwargs()))

    def _generate(self) -> None:
        self._spawn("Writing...", lambda: self.service.generate(self.book_id, self.ch_no, **self._editor_kwargs()))

    def _review(self) -> None:
        self._spawn("Reviewing...", lambda: self.service.review(self.book_id, self.ch_no, **self._editor_kwargs()))

    def _revise(self) -> None:
        self._spawn("Revising...", lambda: self.service.revise(self.book_id, self.ch_no, **self._editor_kwargs()))

    def _continue(self) -> None:
        self._spawn("Writing...", lambda: self.service.continue_generate(self.book_id, self.ch_no, **self._editor_kwargs()))

    def _accept(self) -> None:
        self._spawn("Updating Memory...", lambda: self.service.accept(self.book_id, self.ch_no, **self._editor_kwargs()))

    def _spawn(self, label: str, fn: Callable[[], Any]) -> None:
        if self.busy or not self.book_id:
            return
        self.busy = True
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
                self.steps[key] = ui.label(f"{step_mark('pending')} {label}").classes(step_class("pending"))

    def _reset_steps(self) -> None:
        self._stream_buf = ""
        self._stream_active = False
        for key, label, _stages in TRACK_STEPS:
            widget = self.steps.get(key)
            if widget is None:
                continue
            widget.text = f"{step_mark('pending')} {label}"
            widget.classes(replace=step_class("pending"))

    def _set_step(self, key: str, state: str) -> None:
        widget = self.steps.get(key)
        if widget is None:
            return
        widget.text = f"{step_mark(state)} {step_label(key)}"
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
            self.status_lbl.text = status_text(item)
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
            for btn in self.buttons:
                btn.enable()
            if kind == "fail":
                self.status_lbl.text = message or "Error"
            else:
                self.status_lbl.text = "Ready"
                self._reload_editor()
                self._paint_nav()
                self._paint_inspector()
        flush_tokens()

