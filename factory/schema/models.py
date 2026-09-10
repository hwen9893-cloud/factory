"""Generic story schemas for 玄幻 / 修仙 / 仙侠 / 东方奇幻.

Not bound to one book. All models JSON-serialize, persist, and merge by id.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class SchemaModel(BaseModel):
    """Shared JSON config: ignore unknown keys, coerce aliases, keep extra genre fields out."""

    model_config = {"extra": "ignore", "populate_by_name": True}

    def merge(self, patch: dict[str, Any] | SchemaModel) -> Any:
        data = patch.model_dump(exclude_unset=True) if isinstance(patch, BaseModel) else dict(patch or {})
        update = {key: value for key, value in data.items() if _filled(value)}
        return self.__class__.model_validate({**self.model_dump(), **update})


class ItemRef(SchemaModel):
    """Weapon, artifact, inventory entry, or named resource. A bare string is accepted."""

    name: str
    id: str = ""
    note: str = ""

    @model_validator(mode="before")
    @classmethod
    def _from_str(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"name": value}
        return value or {"name": ""}


class Relationship(SchemaModel):
    target_id: str = ""
    target_name: str = ""
    type: str = ""
    note: str = ""

    @model_validator(mode="before")
    @classmethod
    def _from_str(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"note": value, "type": "related"}
        return value or {}


class Rank(SchemaModel):
    rank: int = 0
    title: str = ""
    duties: str = ""


class Character(SchemaModel):
    id: str = ""
    name: str
    aliases: list[str] = Field(default_factory=list)
    age: str = ""
    gender: str = ""
    faction: str = ""
    location: str = ""
    cultivation_realm: str = ""
    sub_realm: str = ""
    skills: list[str] = Field(default_factory=list)
    techniques: list[str] = Field(default_factory=list)
    weapons: list[ItemRef] = Field(default_factory=list)
    artifacts: list[ItemRef] = Field(default_factory=list)
    inventory: list[ItemRef] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    personality: str = ""
    goals: list[str] = Field(default_factory=list)
    secrets: list[str] = Field(default_factory=list)
    status: str = "alive"
    voice_style: str = ""

    @field_validator("age", mode="before")
    @classmethod
    def _age(cls, value: Any) -> str:
        return "" if value is None else str(value)

    @field_validator("aliases", "skills", "techniques", "goals", "secrets", mode="before")
    @classmethod
    def _str_list(cls, value: Any) -> list[str]:
        return _string_list(value)

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        raw = dict(value)
        if not raw.get("cultivation_realm"):
            raw["cultivation_realm"] = raw.get("realm") or raw.get("realm_id") or ""
        if not raw.get("faction"):
            raw["faction"] = raw.get("sect") or raw.get("sect_id") or ""
        if not raw.get("goals") and raw.get("goal"):
            raw["goals"] = [raw["goal"]] if isinstance(raw["goal"], str) else list(raw["goal"] or [])
        if isinstance(raw.get("personality"), list):
            raw["personality"] = "、".join(str(item) for item in raw["personality"] if item)
        return raw


class CultivationRealm(SchemaModel):
    id: str = ""
    name: str
    order: int = 0
    stages: list[str] = Field(default_factory=list)
    typical_lifespan: str = ""
    notes: str = ""

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        raw = dict(value)
        if not raw.get("order") and raw.get("level") is not None:
            raw["order"] = raw["level"]
        return raw


class BreakthroughRule(SchemaModel):
    from_realm: str = ""
    to_realm: str = ""
    requirements: list[str] = Field(default_factory=list)
    failure_cost: str = ""
    notes: str = ""

    @field_validator("requirements", mode="before")
    @classmethod
    def _req(cls, value: Any) -> list[str]:
        return _string_list(value)


class CultivationResource(SchemaModel):
    name: str
    type: str = ""
    used_for: str = ""
    rarity: str = ""

    @model_validator(mode="before")
    @classmethod
    def _from_str(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"name": value}
        return value or {"name": ""}


class LifespanRule(SchemaModel):
    realm: str = ""
    lifespan: str = ""
    notes: str = ""

    @model_validator(mode="before")
    @classmethod
    def _from_str(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"notes": value}
        return value or {}


class CultivationSystem(SchemaModel):
    realms: list[CultivationRealm] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)
    breakthrough_rules: list[BreakthroughRule] = Field(default_factory=list)
    resources: list[CultivationResource] = Field(default_factory=list)
    lifespan_rules: list[LifespanRule] = Field(default_factory=list)
    power_constraints: list[str] = Field(default_factory=list)

    @field_validator("stages", "power_constraints", mode="before")
    @classmethod
    def _strings(cls, value: Any) -> list[str]:
        return _string_list(value)

    @model_validator(mode="before")
    @classmethod
    def _wrap_realms(cls, value: Any) -> Any:
        if isinstance(value, list):
            return {"realms": value}
        return value or {}


class Faction(SchemaModel):
    id: str = ""
    name: str
    type: str = ""
    hierarchy: list[Rank] = Field(default_factory=list)
    territory: list[str] = Field(default_factory=list)
    allies: list[str] = Field(default_factory=list)
    enemies: list[str] = Field(default_factory=list)
    important_members: list[str] = Field(default_factory=list)

    @field_validator("territory", "allies", "enemies", "important_members", mode="before")
    @classmethod
    def _strings(cls, value: Any) -> list[str]:
        return _string_list(value)

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        raw = dict(value)
        if not raw.get("type"):
            raw["type"] = "sect"
        return raw


class Location(SchemaModel):
    id: str = ""
    name: str
    region: str = ""
    parent_location: str = ""
    description: str = ""
    danger_level: str = ""
    factions: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)

    @field_validator("factions", "resources", mode="before")
    @classmethod
    def _strings(cls, value: Any) -> list[str]:
        return _string_list(value)

    @field_validator("danger_level", mode="before")
    @classmethod
    def _danger(cls, value: Any) -> str:
        return "" if value is None else str(value)

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        raw = dict(value)
        if not raw.get("description"):
            raw["description"] = raw.get("summary") or ""
        if not raw.get("region"):
            raw["region"] = raw.get("area") or ""
        return raw


class PlotThread(SchemaModel):
    id: str = ""
    title: str = ""
    setup_chapter: int | None = None
    status: Literal["open", "active", "resolved", "abandoned"] = "open"
    involved_characters: list[str] = Field(default_factory=list)
    expected_payoff: str = ""
    payoff_chapter: int | None = None
    priority: int = 3

    @field_validator("involved_characters", mode="before")
    @classmethod
    def _chars(cls, value: Any) -> list[str]:
        return _string_list(value)

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"title": value, "status": "open"}
        if not isinstance(value, dict):
            return value
        raw = dict(value)
        if not raw.get("title"):
            raw["title"] = raw.get("text") or raw.get("summary") or ""
        if not raw.get("involved_characters"):
            raw["involved_characters"] = raw.get("related_ids") or raw.get("participants") or []
        if not raw.get("setup_chapter") and raw.get("chapter_no") is not None:
            raw["setup_chapter"] = raw["chapter_no"]
        status = str(raw.get("status") or "open")
        raw["status"] = status if status in {"open", "active", "resolved", "abandoned"} else "open"
        if status == "closed":
            raw["status"] = "resolved"
        return raw


class Foreshadowing(SchemaModel):
    id: str = ""
    clue: str
    inserted_at: int | None = None
    expected_resolution: str = ""
    resolved: bool = False
    resolution: str = ""
    related_thread_id: str = ""

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"clue": value}
        if not isinstance(value, dict):
            return value
        raw = dict(value)
        if not raw.get("clue"):
            raw["clue"] = raw.get("text") or raw.get("hint") or ""
        if raw.get("inserted_at") is None and raw.get("chapter_no") is not None:
            raw["inserted_at"] = raw["chapter_no"]
        return raw


class WorldSetting(SchemaModel):
    """World bible slice: cultivation + map + factions. Legacy realms/sects/places still parse."""

    summary: str = ""
    rules: list[str] = Field(default_factory=list)
    cultivation: CultivationSystem = Field(default_factory=CultivationSystem)
    factions: list[Faction] = Field(default_factory=list)
    locations: list[Location] = Field(default_factory=list)
    artifacts: list[ItemRef] = Field(default_factory=list)

    @field_validator("rules", mode="before")
    @classmethod
    def _rules(cls, value: Any) -> list[str]:
        return _string_list(value)

    @model_validator(mode="before")
    @classmethod
    def _legacy_world(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        raw = dict(value)
        cultivation = dict(raw.get("cultivation") or {})
        if not cultivation.get("realms") and raw.get("realms"):
            cultivation["realms"] = raw["realms"]
        raw["cultivation"] = cultivation
        if not raw.get("factions") and raw.get("sects"):
            raw["factions"] = raw["sects"]
        if not raw.get("locations") and raw.get("places"):
            raw["locations"] = raw["places"]
        return raw

    def to_world_json(self) -> dict[str, Any]:
        """Persist + keep legacy keys so older prompts still read realms/sects/places."""
        payload = self.model_dump(mode="json")
        payload["realms"] = [item.model_dump(mode="json") for item in self.cultivation.realms]
        payload["sects"] = [{"id": item.id, "name": item.name, "type": item.type} for item in self.factions]
        payload["places"] = [{"id": item.id, "name": item.name, "region": item.region} for item in self.locations]
        return payload


class StorySchema(SchemaModel):
    """Full knowledge graph for one book. Collections are generic, not novel-specific types."""

    world: WorldSetting = Field(default_factory=WorldSetting)
    characters: list[Character] = Field(default_factory=list)
    plot_threads: list[PlotThread] = Field(default_factory=list)
    foreshadowing: list[Foreshadowing] = Field(default_factory=list)

    def character_by_id(self, character_id: str) -> Character | None:
        for item in self.characters:
            if item.id == character_id:
                return item
        return None

    def faction_by_id(self, faction_id: str) -> Faction | None:
        for item in self.world.factions:
            if item.id == faction_id or item.name == faction_id:
                return item
        return None


class CharacterRoster(SchemaModel):
    characters: list[Character] = Field(default_factory=list)


def _filled(value: Any) -> bool:
    return value not in (None, "", [], {}, ())


def _string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) if not isinstance(item, str) else item for item in value]


def upsert_by_id(rows: list[Any], item: Any) -> list[Any]:
    key = getattr(item, "id", "") or getattr(item, "name", "") or getattr(item, "clue", "")
    if not key:
        return list(rows) + [item]
    updated: list[Any] = []
    found = False
    for row in rows:
        row_key = getattr(row, "id", "") or getattr(row, "name", "") or getattr(row, "clue", "")
        if row_key == key:
            updated.append(row.merge(item) if hasattr(row, "merge") else item)
            found = True
        else:
            updated.append(row)
    if not found:
        updated.append(item)
    return updated
