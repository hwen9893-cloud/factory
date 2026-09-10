"""Offline fixtures for MockProvider. Not used by real vendors."""

from __future__ import annotations

from typing import Any

MOCK_STRUCTURED: dict[str, dict[str, Any]] = {
    "world": {
        "summary": "青岚宗外门，剑修与风系术法为主。",
        "rules": ["不得自造未登记境界", "死人不得无解释现身"],
        "cultivation": {
            "realms": [
                {"id": "knowledge.realm.0001", "name": "炼气期", "order": 1, "stages": ["初期", "中期", "后期", "圆满"], "typical_lifespan": "百岁"}
            ],
            "stages": ["初期", "中期", "后期", "圆满"],
            "breakthrough_rules": [{"from_realm": "炼气期", "to_realm": "筑基期", "requirements": ["筑基丹"], "failure_cost": "经脉受损"}],
            "resources": [{"name": "灵石", "type": "通货", "used_for": "修炼"}],
            "lifespan_rules": [{"realm": "炼气期", "lifespan": "约百岁"}],
            "power_constraints": ["不可越两大境界硬拼"],
        },
        "factions": [
            {
                "id": "knowledge.sect.0001",
                "name": "青岚宗",
                "type": "sect",
                "hierarchy": [{"rank": 1, "title": "外门弟子"}, {"rank": 2, "title": "执事"}],
                "territory": ["青岚山"],
                "allies": [],
                "enemies": [],
                "important_members": ["knowledge.character.0003"],
            }
        ],
        "locations": [
            {
                "id": "knowledge.place.0001",
                "name": "外门演武场",
                "region": "青岚山",
                "parent_location": "青岚宗",
                "description": "外门公开较技之处",
                "danger_level": "low",
                "factions": ["knowledge.sect.0001"],
                "resources": [],
            }
        ],
        "realms": [{"id": "knowledge.realm.0001", "name": "炼气期", "level": 1}],
        "sects": [{"id": "knowledge.sect.0001", "name": "青岚宗"}],
        "places": [{"id": "knowledge.place.0001", "name": "外门演武场"}],
        "artifacts": [],
    },
    "characters": {
        "characters": [
            {
                "id": "knowledge.character.0001",
                "name": "陆沉",
                "aliases": ["阿沉"],
                "age": "十七",
                "gender": "男",
                "faction": "knowledge.sect.0001",
                "location": "青岚宗外门",
                "cultivation_realm": "炼气期",
                "sub_realm": "中期",
                "skills": ["听风"],
                "techniques": ["青岚剑诀"],
                "weapons": [{"name": "木剑"}],
                "artifacts": [],
                "inventory": [],
                "relationships": [{"target_id": "knowledge.character.0002", "target_name": "赵衡", "type": "rival", "note": "当众被挑衅"}],
                "personality": "克制、隐忍",
                "goals": ["活过外门试炼"],
                "secrets": ["旧伤中残留古剑灵息"],
                "status": "alive",
                "voice_style": "短句、低声",
                "realm": "knowledge.realm.0001",
                "sect": "knowledge.sect.0001",
                "goal": "活过外门试炼",
            },
            {
                "id": "knowledge.character.0002",
                "name": "赵衡",
                "realm": "knowledge.realm.0001",
                "sect": "knowledge.sect.0001",
                "personality": "傲慢",
                "voice_style": "讥讽",
                "status": "alive",
                "goal": "当众踩人",
            },
            {
                "id": "knowledge.character.0003",
                "name": "沈青禾",
                "realm": "knowledge.realm.0002",
                "sect": "knowledge.sect.0001",
                "personality": "冷静",
                "voice_style": "点到为止",
                "status": "alive",
                "goal": "观察异变",
            },
        ]
    },
    "architect": {
        "title": "残灵古剑",
        "premise": "灵根残缺的外门弟子在试炼中被迫反击。",
        "theme": "被剥夺资格的人把资格夺回来",
        "tone": "克制、先抑后扬",
        "protagonist_arc": "从不敢拔剑到当众接剑",
        "volume_beats": [{"volume_no": 1, "title": "外门风起", "dramatic_question": "陆沉能否留下", "climax": "试炼异变"}],
    },
    "outline": {
        "title": "残灵古剑",
        "premise": "灵根残缺的外门弟子在试炼中被迫反击，引出旧伤中的古剑灵息。",
        "volumes": [
            {
                "volume_no": 1,
                "title": "外门风起",
                "chapters": [
                    {
                        "ch_no": 1,
                        "title": "第1章 灵根初鸣",
                        "key_events": ["宗门试炼压迫", "旧伤暴露", "以弱胜强留钩子"],
                        "char_focus": ["knowledge.character.0001"],
                        "hook": "执事注意到不该出现的剑息",
                    },
                    {
                        "ch_no": 2,
                        "title": "第2章 剑息余波",
                        "key_events": ["外门议论", "沈青禾旁观", "禁术代价显现"],
                        "char_focus": ["knowledge.character.0001", "knowledge.character.0003"],
                        "hook": "有人要查他旧伤来历",
                    },
                    {
                        "ch_no": 3,
                        "title": "第3章 试炼加码",
                        "key_events": ["对手联手", "陆沉再出手", "境界松动"],
                        "char_focus": ["knowledge.character.0001", "knowledge.character.0002"],
                        "hook": "内门名额要重新洗牌",
                    },
                ],
            }
        ],
    },
    "volume_plan": {
        "volume_no": 1,
        "title": "外门风起",
        "theme": "资格",
        "chapters": [
            {
                "ch_no": 1,
                "title": "第1章 灵根初鸣",
                "function": "压迫后反击",
                "tension": "high",
                "char_focus": ["knowledge.character.0001"],
                "ending_state": "陆沉被执事盯上",
            }
        ],
    },
    "chapter_plan": {
        "ch_no": 1,
        "title": "第1章 灵根初鸣",
        "goal": "完成试炼中的第一次公开反击",
        "must_not": ["陆沉突然元婴", "赵衡无故死亡"],
        "scenes": [
            {
                "scene_no": 1,
                "location": "青岚宗外门演武场",
                "pov_char": "knowledge.character.0001",
                "present_chars": ["knowledge.character.0001", "knowledge.character.0002"],
                "goal": "建立压迫局面",
                "conflict": "外门弟子当众挑衅",
                "pacing": "fast",
            },
            {
                "scene_no": 2,
                "location": "青岚宗外门演武场",
                "pov_char": "knowledge.character.0001",
                "present_chars": ["knowledge.character.0001", "knowledge.character.0003"],
                "goal": "揭示底牌与代价",
                "conflict": "禁术牵动旧伤",
                "pacing": "medium",
            },
            {
                "scene_no": 3,
                "location": "青岚宗外门演武场",
                "pov_char": "knowledge.character.0001",
                "present_chars": ["knowledge.character.0001", "knowledge.character.0002"],
                "goal": "完成反击并留下危机",
                "conflict": "胜利引来执事注意",
                "pacing": "fast",
            },
        ],
    },
    "continuity": {
        "character_conflicts": [],
        "timeline_conflicts": [],
        "world_rule_conflicts": [],
        "item_conflicts": [],
        "plot_conflicts": [],
        "severity": "none",
        "notes": "mock continuity: no hard canon breaks.",
        "passed": True,
        "issues": [],
    },
    "review": {
        "score": 72,
        "problems": [],
        "strengths": ["任务完成"],
        "must_fix": [],
        "optional_fix": [],
        "pass": True,
        "passed": True,
        "issues": [],
    },
    "memory": {
        "summary": "陆沉在外门试炼中公开反击赵衡，执事开始注意他。",
        "events": [
            {
                "event_name": "演武场反击",
                "chapter_no": 1,
                "participants": ["knowledge.character.0001", "knowledge.character.0002"],
                "outcome": "赵衡受挫，陆沉暴露剑息",
            }
        ],
        "character_changes": [
            {"id": "knowledge.character.0001", "name": "陆沉", "realm": "knowledge.realm.0001", "status": "alive", "note": "旧伤加重"},
            {"id": "knowledge.character.0002", "name": "赵衡", "realm": "knowledge.realm.0001", "status": "alive", "note": "当众受挫"},
        ],
        "new_facts": ["陆沉当众使出完整青岚剑诀"],
        "unresolved_threads": [
            {
                "id": "thread.sword-attention",
                "text": "执事注意到不该出现的剑息",
                "related_ids": ["knowledge.character.0001"],
            }
        ],
        "resolved_threads": [],
        "current_conflict": "外门试炼资格",
        "current_tasks": ["活过执事追查"],
        "timeline_events": [
            {
                "id": "knowledge.timeline.0002",
                "event_name": "演武场反击",
                "chapter_no": 1,
                "participants": ["knowledge.character.0001", "knowledge.character.0002"],
                "outcome": "赵衡受挫，陆沉暴露剑息",
            }
        ],
        "character_state": [
            {"id": "knowledge.character.0001", "name": "陆沉", "realm": "knowledge.realm.0001", "status": "alive", "note": "旧伤加重"},
            {"id": "knowledge.character.0002", "name": "赵衡", "realm": "knowledge.realm.0001", "status": "alive", "note": "当众受挫"},
        ],
        "facts": ["陆沉当众使出完整青岚剑诀"],
    },
}
