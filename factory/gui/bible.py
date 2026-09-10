"""Story Bible — knowledge list + detail. Talks only to FactoryService."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from factory.gui.theme import empty_book, page_header
from factory.service import FactoryService
from factory.settings import Settings

CATEGORIES = (
    ("world", "World"),
    ("characters", "Characters"),
    ("factions", "Factions"),
    ("locations", "Locations"),
    ("cultivation", "Cultivation"),
    ("rules", "Rules"),
)


def build_bible(*, book_id: str | None, settings: Settings) -> None:
    service = FactoryService(settings)
    resolved = service.resolve_book(book_id)
    if not resolved:
        page_header("Story Bible", "bible")
        empty_book()
        return
    BiblePage(service, resolved).render()


class BiblePage:
    def __init__(self, service: FactoryService, book_id: str) -> None:
        self.service = service
        self.book_id = book_id
        self.category = "world"
        self.selected = ""
        self.detail: Any = None
        self.buttons: dict[str, Any] = {}

    def render(self) -> None:
        with ui.element("div").classes("page-shell"):
            page_header("Story Bible", "bible")
            with ui.element("div").classes("page-body"):
                ui.label("设定来自 knowledge/*。此页可手工改并保存，不在这里跑 world_builder。").classes("muted")
                with ui.element("div").classes("split"):
                    with ui.element("div").classes("side-list"):
                        for key, label in CATEGORIES:
                            btn = ui.button(label, on_click=lambda _e=None, k=key: self._select_category(k)).props(
                                "flat dense no-caps"
                            )
                            btn.classes("side-item")
                            self.buttons[key] = btn
                    self.detail = ui.element("div")
        self._paint()

    def _select_category(self, key: str) -> None:
        self.category = key
        self.selected = ""
        self._paint()

    def _paint(self) -> None:
        for key, btn in self.buttons.items():
            btn.classes(replace="side-item active" if key == self.category else "side-item")
        self.detail.clear()
        bible = self.service.story_bible(self.book_id)
        world = bible.get("world") or {}
        with self.detail:
            if self.category == "world":
                self._world(world)
            elif self.category == "characters":
                self._characters(bible.get("characters") or [])
            elif self.category == "factions":
                self._named_list(world.get("factions") or [], "势力")
            elif self.category == "locations":
                self._named_list(world.get("locations") or [], "地点")
            elif self.category == "cultivation":
                self._cultivation(world.get("cultivation") or {})
            else:
                self._rules(world)

    def _world(self, world: dict[str, Any]) -> None:
        ui.label("World").classes("text-h6")
        summary = ui.textarea(value=str(world.get("summary") or ""), label="摘要").classes("w-full")
        rules = ui.textarea(value="\n".join(world.get("rules") or []), label="规则（一行一条）").classes("w-full")
        ui.button("Save", on_click=lambda: self._save_world(summary.value, rules.value)).props("unelevated")

    def _save_world(self, summary: str, rules_text: str) -> None:
        self.service.save_world_bible(
            self.book_id,
            summary=summary,
            rules=[line for line in str(rules_text or "").splitlines() if line.strip()],
        )
        ui.notify("已保存 world.json")
        self._paint()

    def _characters(self, rows: list[dict[str, Any]]) -> None:
        ui.label("Characters").classes("text-h6")
        if not rows:
            ui.label("还没有人物。先 factory architect。").classes("muted")
            return
        with ui.row().classes("w-full"):
            with ui.column().classes("w-40"):
                for item in rows:
                    cid = str(item.get("id") or item.get("name") or "")
                    name = str(item.get("name") or cid)
                    ui.button(name, on_click=lambda _e=None, k=cid: self._show_character(k)).props("flat dense no-caps").classes(
                        "side-item"
                    )
            self.char_box = ui.column().classes("flex-1")
        if not self.selected and rows:
            self._show_character(str(rows[0].get("id") or rows[0].get("name") or ""))

    def _show_character(self, character_id: str) -> None:
        self.selected = character_id
        bible = self.service.story_bible(self.book_id)
        item = next(
            (
                row
                for row in bible.get("characters") or []
                if str(row.get("id") or row.get("name")) == character_id
            ),
            {},
        )
        box = getattr(self, "char_box", None)
        if box is None:
            return
        box.clear()
        with box:
            name = ui.input(value=str(item.get("name") or ""), label="姓名").classes("w-full")
            realm = ui.input(value=str(item.get("cultivation_realm") or ""), label="境界").classes("w-full")
            personality = ui.textarea(value=str(item.get("personality") or ""), label="性格").classes("w-full")
            secrets = ui.textarea(value="\n".join(item.get("secrets") or []), label="秘密").classes("w-full")
            status = ui.input(value=str(item.get("status") or "alive"), label="状态").classes("w-full")
            ui.button(
                "Save",
                on_click=lambda: self._save_character(
                    character_id,
                    {
                        "name": name.value,
                        "cultivation_realm": realm.value,
                        "personality": personality.value,
                        "secrets": [line for line in str(secrets.value or "").splitlines() if line.strip()],
                        "status": status.value,
                    },
                ),
            ).props("unelevated")

    def _save_character(self, character_id: str, patch: dict[str, Any]) -> None:
        self.service.save_character_bible(self.book_id, character_id, patch)
        ui.notify("已保存 characters.json")

    def _named_list(self, rows: list[dict[str, Any]], empty: str) -> None:
        ui.label(empty).classes("text-h6")
        if not rows:
            ui.label(f"暂无{empty}。").classes("muted")
            return
        for item in rows:
            with ui.element("div").classes("info-card mb-2"):
                ui.label(str(item.get("name") or item.get("id") or "")).classes("text-subtitle1")
                extra = item.get("description") or item.get("type") or item.get("region") or ""
                if extra:
                    ui.label(str(extra)).classes("muted")

    def _cultivation(self, cultivation: dict[str, Any]) -> None:
        ui.label("Cultivation").classes("text-h6")
        realms = cultivation.get("realms") or []
        if not realms:
            ui.label("暂无境界表。").classes("muted")
            return
        for item in realms:
            stages = " / ".join(item.get("stages") or [])
            ui.label(f"{item.get('name') or item.get('id')}  {stages}").classes("text-sm")
        rules = cultivation.get("breakthrough_rules") or []
        if rules:
            ui.label("突破规则").classes("text-subtitle2 mt-4")
            for item in rules:
                ui.label(f"{item.get('from_realm')} → {item.get('to_realm')}").classes("muted")

    def _rules(self, world: dict[str, Any]) -> None:
        ui.label("Rules").classes("text-h6")
        rules = world.get("rules") or []
        if not rules:
            ui.label("暂无世界规则。可在 World 分类里编辑。").classes("muted")
            return
        for line in rules:
            ui.label(f"· {line}")
