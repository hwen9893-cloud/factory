"""Versioned Story Bible and Story State contracts for long-form production."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from factory.schema.models import Character, Foreshadowing, PlotThread, WorldSetting

SCHEMA_VERSION = 2


class ContractModel(BaseModel):
    model_config = {"extra": "ignore", "populate_by_name": True}


class FactSource(str, Enum):
    HARD_RULE = "hard_rule"
    AUTHOR = "author"
    FRAMEWORK = "framework"
    FINAL_CHAPTER = "final_chapter"
    AGENT_INFERENCE = "agent_inference"

    @property
    def priority(self) -> int:
        return {
            FactSource.HARD_RULE: 500,
            FactSource.AUTHOR: 400,
            FactSource.FRAMEWORK: 300,
            FactSource.FINAL_CHAPTER: 200,
            FactSource.AGENT_INFERENCE: 100,
        }[self]


class Provenance(ContractModel):
    source_type: FactSource = FactSource.FRAMEWORK
    source_id: str = ""
    source_file: str = ""
    source_hash: str = ""
    source_heading: str = ""
    source_line: int | None = None
    schema_version: int = SCHEMA_VERSION
    imported_at: str = ""
    import_operation_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    confidence: float = 1.0
    locked: bool = False

    @field_validator("confidence")
    @classmethod
    def _confidence(cls, value: float) -> float:
        return min(1.0, max(0.0, float(value)))


class SourcedFact(ContractModel):
    id: str
    text: str
    provenance: Provenance = Field(default_factory=Provenance)


class GoldenFingerGrowthStage(ContractModel):
    id: str
    name: str = ""
    unlock_conditions: list[str] = Field(default_factory=list)
    functions: list[str] = Field(default_factory=list)


class GoldenFingerDefinition(ContractModel):
    id: str
    name: str
    description: str = ""
    mechanism: str = ""
    activation_conditions: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    costs: list[str] = Field(default_factory=list)
    cooldown: str = ""
    limitations: list[str] = Field(default_factory=list)
    growth_stages: list[GoldenFingerGrowthStage] = Field(default_factory=list)
    exposure_risk: str = ""
    forbidden_uses: list[str] = Field(default_factory=list)
    can_do: list[str] = Field(default_factory=list)
    cannot_do: list[str] = Field(default_factory=list)
    initial_state: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance = Field(default_factory=Provenance)


class AntagonistStage(ContractModel):
    id: str
    antagonist_id: str
    stage_no: int = 1
    chapter_range: str = ""
    goal: str = ""
    resources: list[str] = Field(default_factory=list)
    pressure_method: list[str] = Field(default_factory=list)
    escalation: str = ""
    reveal: str = ""
    defeat_condition: str = ""
    next_stage_trigger: str = ""
    status: str = "planned"
    provenance: Provenance = Field(default_factory=Provenance)


class MainPlotPhase(ContractModel):
    id: str
    phase: str
    goal: str = ""
    starting_state: dict[str, Any] = Field(default_factory=dict)
    ending_state: dict[str, Any] = Field(default_factory=dict)
    required_events: list[str] = Field(default_factory=list)
    turning_points: list[str] = Field(default_factory=list)
    foreshadowing: list[str] = Field(default_factory=list)
    payoffs: list[str] = Field(default_factory=list)
    failure_consequences: list[str] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)


class PayoffRule(ContractModel):
    id: str
    type: str
    setup: str = ""
    trigger: str = ""
    payoff: str = ""
    intensity: str = ""
    cooldown_chapters: int = 0
    allowed_frequency: str = ""
    repetition_limit: int = 0
    target_emotion: str = ""
    provenance: Provenance = Field(default_factory=Provenance)


class HookRule(ContractModel):
    id: str
    type: str
    setup: str = ""
    trigger: str = ""
    payoff_window: str = ""
    intensity: str = ""
    cooldown: int = 0
    repetition_limit: int = 0
    provenance: Provenance = Field(default_factory=Provenance)


class StyleGuide(ContractModel):
    pov: str = ""
    tense: str = ""
    sentence_rhythm: str = ""
    paragraph_length: str = ""
    dialogue_ratio: str = ""
    description_density: str = ""
    preferred_vocabulary: list[str] = Field(default_factory=list)
    banned_phrases: list[str] = Field(default_factory=list)
    humor_level: str = ""
    violence_scale: str = ""
    chapter_opening_style: str = ""
    chapter_ending_style: str = ""


class StoryBible(ContractModel):
    schema_version: int = SCHEMA_VERSION
    title: str = ""
    genre: str = ""
    premise: str = ""
    world: WorldSetting = Field(default_factory=WorldSetting)
    characters: list[Character] = Field(default_factory=list)
    golden_fingers: list[GoldenFingerDefinition] = Field(default_factory=list)
    antagonist_stages: list[AntagonistStage] = Field(default_factory=list)
    main_plot_phases: list[MainPlotPhase] = Field(default_factory=list)
    volume_plans: list[dict[str, Any]] = Field(default_factory=list)
    chapter_outlines: list[dict[str, Any]] = Field(default_factory=list)
    plot_threads: list[PlotThread] = Field(default_factory=list)
    foreshadowing: list[Foreshadowing] = Field(default_factory=list)
    payoff_rules: list[PayoffRule] = Field(default_factory=list)
    hook_rules: list[HookRule] = Field(default_factory=list)
    style_guide: StyleGuide = Field(default_factory=StyleGuide)
    forbidden_rules: list[str] = Field(default_factory=list)
    facts: list[SourcedFact] = Field(default_factory=list)


class CharacterKnowledgeState(ContractModel):
    character_id: str
    known_facts: list[str] = Field(default_factory=list)
    suspected_facts: list[str] = Field(default_factory=list)
    false_beliefs: list[str] = Field(default_factory=list)
    secrets_known: list[str] = Field(default_factory=list)
    last_updated_chapter: int = 0


class GoldenFingerState(ContractModel):
    golden_finger_id: str
    current_stage: str = ""
    energy: float | None = None
    cooldown_until: int | None = None
    usage_count: int = 0
    known_functions: list[str] = Field(default_factory=list)
    unlocked_functions: list[str] = Field(default_factory=list)
    exposure_level: str = ""


class LedgerEntry(ContractModel):
    type: str
    chapter_no: int
    intensity: str = ""
    target: str = ""
    status: str = "used"
    source_plan_id: str = ""


class StoryState(ContractModel):
    schema_version: int = SCHEMA_VERSION
    state_version: int = 0
    current_chapter: int = 1
    current_time: str = ""
    characters: dict[str, dict[str, Any]] = Field(default_factory=dict)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    character_knowledge: dict[str, CharacterKnowledgeState] = Field(default_factory=dict)
    golden_fingers: dict[str, GoldenFingerState] = Field(default_factory=dict)
    current_main_plot_phase: str = ""
    current_antagonist_stage: str = ""
    current_conflict: str = ""
    events: list[dict[str, Any]] = Field(default_factory=list)
    open_threads: list[dict[str, Any]] = Field(default_factory=list)
    resolved_threads: list[dict[str, Any]] = Field(default_factory=list)
    placed_foreshadowing: list[str] = Field(default_factory=list)
    resolved_foreshadowing: list[str] = Field(default_factory=list)
    hook_ledger: list[LedgerEntry] = Field(default_factory=list)
    payoff_ledger: list[LedgerEntry] = Field(default_factory=list)
    applied_operations: list[str] = Field(default_factory=list)


class EntityChange(ContractModel):
    id: str
    patch: dict[str, Any] = Field(default_factory=dict)


class StoryStateDelta(ContractModel):
    operation_id: str
    chapter_no: int
    base_state_version: int
    character_changes: list[EntityChange] = Field(default_factory=list)
    relationship_changes: list[dict[str, Any]] = Field(default_factory=list)
    inventory_changes: list[dict[str, Any]] = Field(default_factory=list)
    cultivation_changes: list[dict[str, Any]] = Field(default_factory=list)
    location_changes: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_changes: list[dict[str, Any]] = Field(default_factory=list)
    timeline_events: list[dict[str, Any]] = Field(default_factory=list)
    new_facts: list[str] = Field(default_factory=list)
    new_threads: list[dict[str, Any]] = Field(default_factory=list)
    resolved_threads: list[str] = Field(default_factory=list)
    foreshadowing_changes: list[dict[str, Any]] = Field(default_factory=list)
    golden_finger_changes: list[EntityChange] = Field(default_factory=list)
    villain_stage_changes: list[dict[str, Any]] = Field(default_factory=list)
    main_plot_changes: list[dict[str, Any]] = Field(default_factory=list)
    hook_ledger_changes: list[LedgerEntry] = Field(default_factory=list)
    payoff_ledger_changes: list[LedgerEntry] = Field(default_factory=list)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

