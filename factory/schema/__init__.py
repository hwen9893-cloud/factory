"""Generic, JSON-serializable story schemas. Not bound to a specific novel."""

from factory.schema.models import (
    BreakthroughRule,
    Character,
    CharacterRoster,
    CultivationRealm,
    CultivationResource,
    CultivationSystem,
    Faction,
    Foreshadowing,
    ItemRef,
    LifespanRule,
    Location,
    PlotThread,
    Relationship,
    StorySchema,
    WorldSetting,
    upsert_by_id,
)
from factory.schema.store import SchemaStore

__all__ = [
    "BreakthroughRule",
    "Character",
    "CharacterRoster",
    "CultivationRealm",
    "CultivationResource",
    "CultivationSystem",
    "Faction",
    "Foreshadowing",
    "ItemRef",
    "LifespanRule",
    "Location",
    "PlotThread",
    "Relationship",
    "SchemaStore",
    "StorySchema",
    "WorldSetting",
    "upsert_by_id",
]
