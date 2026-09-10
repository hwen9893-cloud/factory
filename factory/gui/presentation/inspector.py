"""Inspector panel mapping. Core DTOs in, markdown/copy out."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

MEMORY_PREVIEW_NOTE = (
    "生成本章后 Memory Agent 会更新：canon facts、人物状态、开放线索、近章摘要。"
)


@dataclass(frozen=True)
class InspectorView:
    plan: dict[str, Any] | None
    context: dict[str, Any]
    review: dict[str, Any] | None
    continuity: dict[str, Any] | None
    memory: dict[str, Any]


def build_inspector_view(
    *,
    plan: dict[str, Any] | None,
    context: dict[str, Any],
    review: dict[str, Any] | None,
    continuity: dict[str, Any] | None,
    memory: dict[str, Any],
) -> InspectorView:
    return InspectorView(
        plan=plan,
        context=context,
        review=review,
        continuity=continuity,
        memory=memory,
    )


def chapter_version_label(source: str, revision: int, pipeline_status: str) -> str:
    version = f"{source} · rev {revision}" if revision else source
    if pipeline_status and pipeline_status not in {source, ""}:
        version = f"{version} · {pipeline_status}"
    return version


def plan_md(plan: dict[str, Any] | None) -> str:
    if not plan:
        return "_尚未规划_"
    heading = str(plan.get("title") or f"第{plan.get('ch_no')}章")
    lines = [f"**{heading}**"]
    if plan.get("goal"):
        lines.append(f"\n目标：{plan['goal']}")
    scenes = plan.get("scenes") or []
    if scenes:
        lines.append("\n**Scenes**")
        for scene in scenes:
            if isinstance(scene, dict):
                lines.append(
                    f"- {scene.get('location') or ''} · {scene.get('pov_char') or ''} · {scene.get('goal') or ''}".strip(" ·")
                )
            else:
                lines.append(f"- {scene}")
    forbidden = plan.get("must_not") or []
    if forbidden:
        lines.append("\n**Must not**")
        lines.extend(f"- {item}" for item in forbidden)
    return "\n".join(lines)


def context_md(ctx: dict[str, Any]) -> str:
    lines = ["### Characters"]
    characters = ctx.get("characters") or []
    if characters:
        for item in characters:
            if isinstance(item, dict):
                lines.append(
                    f"- **{item.get('name') or item.get('id')}** — {item.get('status') or ''} {item.get('note') or item.get('personality') or ''}".strip()
                )
            else:
                lines.append(f"- {item}")
    else:
        lines.append("_（无）_")
    lines.append("\n### Plot")
    plot = ctx.get("plot") or []
    if isinstance(plot, list):
        if plot:
            for item in plot:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('text') or item.get('title') or item}")
                else:
                    lines.append(f"- {item}")
        else:
            lines.append("_（无）_")
    else:
        lines.append(f"```\n{_short_json(plot)}\n```")
    lines.append("\n### World")
    world = ctx.get("world") or {}
    if isinstance(world, dict):
        summary = world.get("world_summary") or world.get("summary") or ""
        lines.append(summary or "_（无）_")
        rules = world.get("rules") or []
        lines.extend(f"- {item}" for item in rules[:8])
    else:
        lines.append(str(world) or "_（无）_")
    lines.append("\n### Recent context")
    lines.append(str(ctx.get("recent_context") or "_（无）_"))
    return "\n".join(lines)


def review_md(review: dict[str, Any] | None) -> str:
    if not review:
        return "_尚未审稿_"
    passed = review.get("pass", review.get("passed", True))
    lines = [f"**Score {review.get('score', '—')}**  ·  {'pass' if passed else 'fail'}"]
    must = review.get("must_fix") or []
    if must:
        lines.append("\n**Must fix**")
        lines.extend(f"- {item}" for item in must)
    problems = review.get("problems") or []
    if problems:
        lines.append("\n**Problems**")
        lines.extend(f"- {item}" for item in problems)
    suggestions = review.get("optional_fix") or review.get("suggestions") or []
    if suggestions:
        lines.append("\n**Suggestions**")
        lines.extend(f"- {item}" for item in suggestions)
    return "\n".join(lines)


def continuity_md(report: dict[str, Any] | None) -> str:
    if not report:
        return "_尚未检查_"
    buckets = (
        ("人物冲突", "character_conflicts"),
        ("时间冲突", "timeline_conflicts"),
        ("世界观冲突", "world_rule_conflicts"),
        ("物品冲突", "item_conflicts"),
        ("剧情冲突", "plot_conflicts"),
    )
    lines = [f"severity: **{report.get('severity') or 'none'}**"]
    for title, key in buckets:
        items = report.get(key) or []
        lines.append(f"\n### {title}")
        if items:
            for item in items:
                if isinstance(item, dict):
                    lines.append(f"- [{item.get('severity') or 'warn'}] {item.get('message') or item}")
                else:
                    lines.append(f"- {item}")
        else:
            lines.append("_无_")
    return "\n".join(lines)


def memory_md(memory: dict[str, Any]) -> str:
    if not memory.get("applied"):
        return MEMORY_PREVIEW_NOTE
    lines = ["已写入本章记忆。"]
    if memory.get("summary"):
        lines.append(f"\n**Summary**\n{memory['summary']}")
    for title, key in (
        ("人物变化", "character_changes"),
        ("新事实", "new_facts"),
        ("开放线索", "unresolved_threads"),
        ("已回收线索", "resolved_threads"),
        ("当前任务", "current_tasks"),
    ):
        items = memory.get(key) or []
        if not items:
            continue
        lines.append(f"\n**{title}**")
        for item in items:
            if isinstance(item, dict):
                lines.append(f"- {item.get('text') or item.get('name') or item}")
            else:
                lines.append(f"- {item}")
    if memory.get("current_conflict"):
        lines.append(f"\n**冲突**\n{memory['current_conflict']}")
    return "\n".join(lines)


def memory_layers_md(overview: dict[str, Any], foreshadowing: list[dict[str, Any]]) -> str:
    canon = overview.get("canon") or {}
    lines = [
        "### Global Canon",
        str(canon.get("world_summary") or "_尚无世界摘要_"),
    ]
    rules = canon.get("rules") or []
    if rules:
        lines.append("\n**规则**")
        lines.extend(f"- {item}" for item in rules)
    facts = canon.get("facts") or []
    if facts:
        lines.append("\n**永久事实**")
        lines.extend(f"- {item}" for item in facts)

    lines.append("\n### Characters State")
    characters = overview.get("characters") or []
    if not characters:
        lines.append("尚无人物状态（定稿后 Memory Agent 会更新）。")
    for item in characters:
        bits = [item.get("name") or item.get("id")]
        if item.get("realm"):
            bits.append(str(item["realm"]))
        if item.get("location"):
            bits.append(str(item["location"]))
        if item.get("status"):
            bits.append(str(item["status"]))
        lines.append("- " + " · ".join(str(part) for part in bits if part))

    lines.append("\n### Plot Threads")
    if overview.get("conflict"):
        lines.append(f"当前冲突：{overview['conflict']}")
    threads = overview.get("threads") or []
    if not threads:
        lines.append("无开放线索。")
    for item in threads:
        lines.append(f"- {item.get('text') or item.get('id')} (`{item.get('status')}`)")

    lines.append("\n### Foreshadowing")
    if not foreshadowing:
        lines.append("无伏笔记录。")
    for item in foreshadowing:
        state = "resolved" if item.get("resolved") else "open"
        lines.append(f"- {item.get('clue') or item.get('id')} (`{state}`)")

    n = overview.get("recent_n") or 3
    lines.append(f"\n### Recent Memory（近 {n} 章）")
    recent = overview.get("recent") or []
    if not recent:
        lines.append("尚无近章摘要。")
    for item in recent:
        lines.append(f"- ch{int(item.get('ch_no') or 0):03d}  {item.get('summary') or ''}")
    return "\n".join(lines)


def _short_json(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2)
    if len(text) > 1200:
        return text[:1200] + "\n…"
    return text
