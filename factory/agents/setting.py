"""Setting agents: world bible and character roster. They do not write chapters."""

from __future__ import annotations

from typing import Any

from factory.agents.base import BaseAgent
from factory.schema.models import CharacterRoster, WorldSetting
from factory.schema.store import SchemaStore

WORLD_SCHEMA = WorldSetting.model_json_schema()
CHARACTER_SCHEMA = CharacterRoster.model_json_schema()


class WorldBuilderAgent(BaseAgent):
    """Maintain the world bible. Does not invent chapter plots."""

    name = "world_builder"
    model = "architect"
    prompt_name = "world_builder"
    temperature = 0.4
    required_inputs = ("story_seed",)
    required_outputs = ("world",)
    output_schema = WORLD_SCHEMA

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        world = WorldSetting.model_validate(self.ask_json(purpose="world"))
        payload = world.to_world_json()
        self.context.world = payload
        SchemaStore(self.repo, self.context.book_id).save_world(world)
        self._sync_canon()
        return {"world": payload}


class CharacterAgent(BaseAgent):
    """Maintain the character database. Does not write prose or outlines."""

    name = "character"
    model = "architect"
    prompt_name = "character"
    temperature = 0.5
    required_inputs = ("story_seed",)
    required_outputs = ("characters",)
    output_schema = CHARACTER_SCHEMA

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        roster = CharacterRoster.model_validate(self.ask_json(purpose="characters"))
        store = SchemaStore(self.repo, self.context.book_id)
        characters = [store.upsert_character(item).model_dump(mode="json") for item in roster.characters]
        self.context.characters = characters
        if not self.context.character_state:
            self.context.character_state = [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "realm": item.get("cultivation_realm") or item.get("realm"),
                    "status": item.get("status", "alive"),
                }
                for item in characters
            ]
            self.repo.save_character_state(self.context.book_id, self.context.character_state)
        self._sync_canon()
        return {"characters": characters}
