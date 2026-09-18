from __future__ import annotations

from factory.framework.models import ImportIssue, ParsedFramework
from factory.schema.contracts import StoryBible


class SchemaValidator:
    def validate(self, parsed: ParsedFramework) -> list[ImportIssue]:
        try:
            StoryBible.model_validate(parsed.bible.model_dump(mode="json"))
        except Exception as exc:
            return [ImportIssue(level="error", code="SCHEMA_ERROR", message=str(exc))]
        return []


class ReferenceValidator:
    def validate(self, bible: StoryBible) -> list[ImportIssue]:
        issues: list[ImportIssue] = []
        characters = {item.id for item in bible.characters if item.id}
        factions = {item.id for item in bible.world.factions if item.id}
        locations = {item.id for item in bible.world.locations if item.id}
        realms = {item.id for item in bible.world.cultivation.realms if item.id}
        golden = {item.id for item in bible.golden_fingers}
        for item in bible.characters:
            self._ref(issues, item.id, "faction", item.faction, factions)
            self._ref(issues, item.id, "realm", item.cultivation_realm, realms)
            self._ref(issues, item.id, "location", item.location, locations)
        for item in bible.antagonist_stages:
            self._ref(issues, item.id, "antagonist", item.antagonist_id, characters)
        for item in bible.world.cultivation.realms:
            self._ref(issues, item.id, "previous realm", item.previous, realms)
            self._ref(issues, item.id, "next realm", item.next, realms)
        for item in bible.golden_fingers:
            for stage in item.growth_stages:
                if not stage.id:
                    issues.append(ImportIssue(level="error", code="INVALID_REFERENCE", message=f"{item.id} 存在无 ID 成长阶段", entity_id=item.id))
        for chapter in bible.chapter_outlines:
            for key, valid in (("characters", characters), ("locations", locations)):
                for ref in chapter.get(key) or []:
                    self._ref(issues, str(chapter.get("id") or "chapter"), key, str(ref), valid)
        for clue in bible.foreshadowing:
            if clue.related_thread_id and clue.related_thread_id not in {item.id for item in bible.plot_threads}:
                self._ref(issues, clue.id, "thread", clue.related_thread_id, {item.id for item in bible.plot_threads})
        del golden
        return issues

    @staticmethod
    def _ref(issues: list[ImportIssue], owner: str, field: str, target: str, valid: set[str]) -> None:
        if target and target not in valid:
            issues.append(ImportIssue(level="error", code="UNRESOLVED_REFERENCE", message=f"{owner}.{field} 引用了不存在的 {target}", entity_id=owner))

