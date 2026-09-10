"""Load / save / update StorySchema. Knowledge files stay JSON; models stay generic."""

from __future__ import annotations

from typing import Any

from factory.schema.models import (
    Character,
    Foreshadowing,
    PlotThread,
    StorySchema,
    WorldSetting,
    upsert_by_id,
)
from factory.storage import BookRepository


class SchemaStore:
    """Persists the story bible beside existing knowledge/*.json files."""

    def __init__(self, repo: BookRepository, book_id: str) -> None:
        self.repo = repo
        self.book_id = book_id

    def load(self) -> StorySchema:
        world = WorldSetting.model_validate(self.repo.load_world(self.book_id) or {})
        characters = [Character.model_validate(item) for item in self.repo.load_characters(self.book_id) or [] if item]
        plot = self.repo.load_plot(self.book_id)
        threads = [PlotThread.model_validate(item) for item in plot.get("plot_threads") or []]
        clues = [Foreshadowing.model_validate(item) for item in plot.get("foreshadowing") or []]
        return StorySchema(world=world, characters=characters, plot_threads=threads, foreshadowing=clues)

    def save(self, schema: StorySchema) -> None:
        self.save_world(schema.world)
        self.save_characters(schema.characters)
        self.save_plot(schema.plot_threads, schema.foreshadowing)

    def save_world(self, world: WorldSetting) -> None:
        self.repo.save_world(self.book_id, world.to_world_json())

    def save_characters(self, characters: list[Character]) -> None:
        self.repo.save_characters(self.book_id, [item.model_dump(mode="json") for item in characters])

    def save_plot(self, threads: list[PlotThread], clues: list[Foreshadowing]) -> None:
        self.repo.save_plot(
            self.book_id,
            {
                "plot_threads": [item.model_dump(mode="json") for item in threads],
                "foreshadowing": [item.model_dump(mode="json") for item in clues],
            },
        )

    def update_character(self, character_id: str, patch: dict[str, Any] | Character) -> Character:
        schema = self.load()
        current = schema.character_by_id(character_id)
        incoming = patch if isinstance(patch, Character) else Character.model_validate({"name": character_id, **dict(patch), "id": character_id})
        merged = current.merge(incoming) if current else incoming
        if not merged.id:
            merged = merged.model_copy(update={"id": character_id})
        schema.characters = upsert_by_id(schema.characters, merged)
        self.save_characters(schema.characters)
        return merged

    def upsert_character(self, character: Character) -> Character:
        schema = self.load()
        schema.characters = upsert_by_id(schema.characters, character)
        self.save_characters(schema.characters)
        found = schema.character_by_id(character.id) or character
        return found

    def upsert_plot_thread(self, thread: PlotThread) -> PlotThread:
        schema = self.load()
        schema.plot_threads = upsert_by_id(schema.plot_threads, thread)
        self.save_plot(schema.plot_threads, schema.foreshadowing)
        return next((item for item in schema.plot_threads if item.id == thread.id or item.title == thread.title), thread)

    def upsert_foreshadowing(self, clue: Foreshadowing) -> Foreshadowing:
        schema = self.load()
        schema.foreshadowing = upsert_by_id(schema.foreshadowing, clue)
        self.save_plot(schema.plot_threads, schema.foreshadowing)
        return next((item for item in schema.foreshadowing if item.id == clue.id or item.clue == clue.clue), clue)
