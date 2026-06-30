# 43 - factory.novel 流水线详细规范

> Version：v1.1　Last Update：2026-06
> Status：Active
> 依赖：`12-术语与Skill规范.md`、`34-center.model接口规范.md`、`41-修仙爽文角色量化系统.md`、`42-知识库设定规范.md`、`61-数据契约与Schema.md`、`62-AgentSkills实现规范.md`

---

# 1. 流水线总览

```
[idea / story_seed]
        │
        ▼
skill.novel.outline   → 生成全卷大纲（章标题 + 主要事件）
        │
        ▼  ← 人在环：剧情设计审核大纲
skill.novel.plot      → 逐章分解场景卡（每章 3–5 张）
        │
        ▼
skill.novel.chapter   → 按场景卡生成正文（≥3000字/章）
        │
        ▼
skill.novel.dialogue  → 提炼/润色对话，注入角色声线
        │
        ▼
skill.qa.consistency  → 设定冲突校验（对比 center.knowledge）
        │ ─── 冲突 → 回到 chapter（最多重试 2 次）
        │ ─── 通过
        ▼
skill.novel.export       → 输出 txt / epub / 平台格式
        │
        ▼
skill.novel.screenplay   → 逐章转换为多维剧本卡
                           （画面·构图·动作·表情·情绪·心理·对话·音效·特效）
                           ↓ 产物供 factory.visual / factory.animation 使用
```

---

# 2. 各 Skill 详细规范

## 2.1 skill.novel.outline

**职责**：基于故事种子与世界观设定，生成全卷结构化大纲。

### Input Schema
```json
{
  "story_seed":    "string（核心钩子，≤500字）",
  "world_refs":   ["knowledge.realm.0001", "knowledge.sect.*"],
  "char_refs":    ["knowledge.character.0001", "..."],
  "volume_no":    "integer（第几卷）",
  "target_chapters": "integer（目标章数，默认 30）"
}
```

### Output Schema
```json
{
  "outline_id":   "factory_novel_outline 表主键",
  "volume_no":    "integer",
  "chapters": [
    {
      "ch_no":    "integer",
      "title":    "string",
      "key_events": ["string × 2–4"],
      "char_focus": ["knowledge.character.ID"],
      "realm_progress": "string（境界变化，可空）",
      "爽点类型":  "string（打脸/装逼/突破/护短/…）"
    }
  ],
  "lineage": { "input_ids": [...], "skill": "skill.novel.outline", "model": "..." }
}
```

### Prompt 策略
- system prompt → 见 `44-Prompt库.md` §1
- 注入：`story_seed` + 角色七维分摘要 + 境界体系 + 宗门关系
- 要求每章标注**爽点类型**，确保每 3 章内有一个 A 层（爽感引擎）触发
- 生成后写入 `factory_novel_outline`，通知人在环审核

---

## 2.2 skill.novel.plot

**职责**：将单章大纲拆解为 3–5 张**场景卡**（Scene Cards），作为 chapter skill 的直接输入。

### Input Schema
```json
{
  "outline_id":  "factory_novel_outline 主键",
  "ch_no":       "integer",
  "prev_tail":   "string（上章最后 200 字，维持衔接）",
  "char_refs":   ["knowledge.character.ID"],
  "timeline_ref":"knowledge.timeline.ID（当前章对应时间点）"
}
```

### Output Schema（场景卡数组）
```json
{
  "plot_id":  "factory_novel_plot 主键",
  "ch_no":    "integer",
  "scenes": [
    {
      "scene_no":    "integer（章内序号）",
      "location":    "knowledge.place.ID 或 string",
      "pov_char":    "knowledge.character.ID（视角角色）",
      "present_chars":["knowledge.character.ID"],
      "goal":        "string（本场景要达成的叙事目标）",
      "conflict":    "string（张力来源）",
      "pacing":      "fast | medium | slow",
      "爽点":        "string（可空）",
      "word_budget": "integer（建议字数，合计≥3000）"
    }
  ],
  "lineage": { ... }
}
```

### plot vs chapter 职责边界
| | skill.novel.plot | skill.novel.chapter |
|--|------|------|
| 输入 | 章大纲（标题+事件） | 场景卡数组 |
| 输出 | 场景卡（结构） | 正文（prose） |
| 长度 | 每卡约 80 字 | ≥ 3000 字/章 |
| 模型 | `novel_review` profile（快） | `novel_write` profile（强） |

---

## 2.3 skill.novel.chapter

**职责**：按场景卡逐场景生成正文，维持设定一致与叙事连续。

### Input Schema
```json
{
  "plot_id":       "factory_novel_plot 主键",
  "ch_no":         "integer",
  "scene_nos":     [1, 2, 3],
  "knowledge_snapshot": {
    "characters":  {"knowledge.character.0001": { /* payload */ }},
    "realm":       {"knowledge.realm.0001": { /* payload */ }},
    "timeline_state": "string（截至上章的时间线摘要）"
  },
  "prev_tail":     "string（上章最后 300 字）",
  "style_hints":   ["string（爽文风格约束，见 44）"]
}
```

### Output Schema
```json
{
  "chapter_id":   "factory_novel_chapter 主键",
  "ch_no":        "integer",
  "title":        "string",
  "body":         "string（≥3000字正文）",
  "word_count":   "integer",
  "new_knowledge":[ /* 新出现的设定变动，待写回 center.knowledge */ ],
  "realm_changes":[ /* 境界变化事件 */ ],
  "lineage": { ... }
}
```

### 连续性维护策略
1. `prev_tail`（上章结尾）始终注入，保证文气衔接。
2. `knowledge_snapshot` 由 skill 在调用前**实时从 `center.knowledge` 快照**，而非缓存。
3. 生成后 `new_knowledge` 字段由 `skill.qa.consistency` 校验后**批量写回** `center.knowledge`。
4. 每章生成后自动更新 `knowledge.timeline` 对应时间点。

---

## 2.4 skill.novel.dialogue

**职责**：对 chapter 输出中的对话段落做**声线校准**，确保每个角色说话风格一致。

### Input Schema
```json
{
  "chapter_id":  "factory_novel_chapter 主键",
  "char_voices": {
    "knowledge.character.0001": "string（声线描述，见 44 §4）"
  }
}
```

### Output Schema
```json
{
  "chapter_id":  "同输入",
  "body":        "string（润色后正文，替换原 chapter.body）",
  "changes":     "integer（修改的对话段落数）",
  "lineage": { ... }
}
```

> 此 skill 是轻量后处理，可选；对话比重低的场景（旁白为主）可跳过。

---

## 2.5 skill.qa.consistency

**职责**：检查生成文本是否与 `center.knowledge` 存在设定冲突，输出冲突列表供 LangGraph 路由。

### Input Schema
```json
{
  "chapter_id":    "factory_novel_chapter 主键",
  "body":          "string（待校验正文）",
  "knowledge_refs":["knowledge.character.*", "knowledge.timeline.*"]
}
```

### Output Schema
```json
{
  "passed":     "boolean",
  "conflicts": [
    {
      "type":   "attribute | timeline | realm | relation | naming",
      "desc":   "string（冲突描述）",
      "ref_id": "knowledge.*.ID（冲突涉及的知识条目）",
      "severity":"hard | soft"
    }
  ],
  "lineage": { ... }
}
```

### 实现方式
- **规则层（优先）**：用 SQL 查 `center_knowledge_item` 做属性/时间线比对（快，召回高）。
- **LLM 层（兜底）**：规则层漏检时，用 `novel_review` profile + 规则集 prompt 做二次确认。
- **路由逻辑**：
  - `hard` 冲突存在 → `passed=false` → LangGraph 回到 chapter（最多 2 次）
  - 仅 `soft` 冲突 → `passed=true` + 写冲突日志供人工复盘
  - 2 次重试仍 hard 冲突 → 置任务状态 `needs_human`，暂停流水线

---

## 2.6 skill.novel.export

**职责**：将审校通过的章节格式化为发布格式。

### Input Schema
```json
{
  "chapter_ids": ["factory_novel_chapter 主键列表"],
  "formats":     ["txt", "epub", "fanqie_md"]
}
```

### Output Schema
```json
{
  "exports": [
    { "format": "txt",  "asset_id": "asset.export.0001", "storage_uri": "..." },
    { "format": "epub", "asset_id": "asset.export.0002", "storage_uri": "..." }
  ],
  "lineage": { ... }
}
```

---

## 2.7 skill.novel.screenplay

**职责**：将通过 QA 的章节正文分解为**多维剧本卡（Beat Cards）**，以画面语言重新呈现故事，作为 `factory.visual` 与 `factory.animation` 的直接输入规格。

每张卡对应一个叙事节拍（beat），覆盖视觉、声音、情绪全维度，可直接驱动 AI 生图和分镜生成。

### Input Schema
```json
{
  "chapter_id":        "factory_novel_chapter 主键",
  "body":              "string（章节正文）",
  "plot_id":           "factory_novel_plot 主键（取场景卡对应关系）",
  "knowledge_snapshot":{
    "characters":      {"knowledge.character.ID": { /* payload */ }},
    "places":          {"knowledge.place.ID": { /* payload */ }}
  },
  "style_ref":         "string（美术风格指令，如'墨骨动漫风·青绿色调'，可空）"
}
```

### Output Schema（剧本卡数组）
```json
{
  "screenplay_id":  "factory_novel_screenplay 主键",
  "chapter_id":     "string",
  "ch_no":          "integer",
  "beats": [
    {
      "beat_no":    "integer（章内序号，从 1 起）",
      "scene_ref":  "string（对应 plot 的 scene_no，可空）",
      "word_range": "string（对应正文段落范围，如 '第 3–5 自然段'）",

      "visual": {
        "location_desc":  "string（地点+背景视觉描述，供生图用）",
        "time_atmosphere":"string（时间、光线、氛围色调，如'黄昏·逆光·血色天际'）",
        "color_palette":  ["string（主色调关键词）"],
        "key_props":      ["string（画面内关键道具/场景元素）"],
        "special_fx":     "string（特效标注：法术光效/爆炸/结界等，可空）"
      },

      "composition": {
        "shot_type":      "close-up|medium-shot|wide-shot|extreme-wide|extreme-close",
        "camera_angle":   "eye-level|high-angle|low-angle|dutch-tilt|bird-eye|worm-eye",
        "camera_movement":"static|pan|tilt|zoom-in|zoom-out|tracking|dolly|crane",
        "focus_subject":  "string（焦点主体）",
        "foreground":     "string（前景元素，可空）",
        "background":     "string（背景层次描述）"
      },

      "characters": [
        {
          "char_ref":      "knowledge.character.ID",
          "frame_position":"string（如'左侧三分之一，全身'）",
          "posture":       "string（姿态/站位，如'半跪·低头'）",
          "action":        "string（动作描述，精确到肢体细节）",
          "expression":    "string（表情描述，如'嘴角微扬·眼神冷峻'）",
          "emotion_state": "string（内在情绪标签，如'克制的愤怒'）",
          "gaze":          "string（视线方向与对象）",
          "costume_note":  "string（服装/法宝特殊状态，可空）"
        }
      ],

      "dialogue": [
        {
          "char_ref":  "knowledge.character.ID",
          "line":      "string（台词原文）",
          "delivery":  "string（语气/语速/音量：低沉·缓慢/激动·颤抖 等）",
          "subtext":   "string（台词潜台词/隐含含义，供配音/字幕二次创作参考）"
        }
      ],

      "inner_monologue": [
        {
          "char_ref": "knowledge.character.ID",
          "thought":  "string（内心独白 OS，画外音或字幕形式）",
          "tone":     "string（独白情绪基调：自嘲/坚定/恐惧/复仇 等）"
        }
      ],

      "sound": {
        "bgm_hint":   "string（音乐情绪指令，如'低沉弦乐·渐强'，可空）",
        "sfx_list":   ["string（音效提示：剑鸣/雷声/心跳 等）"],
        "ambient":    "string（环境音描述，如'风声·远处厮杀'，可空）"
      },

      "pacing":          "fast|medium|slow",
      "duration_est_sec":"integer（预估画面/镜头时长，秒）",
      "爽点":             "string（本 beat 的爽点类型，可空）",
      "animation_notes": "string（给动画师的额外注记，可空）"
    }
  ],
  "total_beats":    "integer",
  "est_duration_sec":"integer（全章预估总时长）",
  "lineage": { "input_ids": ["chapter_id", "plot_id"], "skill": "skill.novel.screenplay", "model": "..." }
}
```

### 拆 beat 策略
| 拆分触发条件 | 说明 |
|------------|------|
| 场景切换 | 地点/时间发生转换时强制新 beat |
| 对话轮次 ≥ 3 | 对话密集段每 2–3 轮一个 beat，保持镜头节奏感 |
| 情绪大幅转折 | 爽感触发点（打脸/突破/翻盘）单独成 beat |
| 动作序列 | 战斗/施法等高速序列每个关键动作独立 beat |
| 内心独白段 | 心理描写为主时单独成 beat（close-up + OS） |

目标：每章 3000 字对应约 **15–30 个 beat**（视节奏快慢），单 beat 预估 5–15 秒。

### 与下游 factory 的契约
```
skill.novel.screenplay 输出 ──► factory.visual
  └─ beats[*].visual + composition + characters → 生图 prompt 直接注入
  └─ beats[*].characters[*].char_ref → AssetID 查角色 LoRA

skill.novel.screenplay 输出 ──► factory.animation
  └─ beats[*] 对应一个分镜帧
  └─ camera_movement + duration_est_sec → 镜头运动规格
  └─ sound.*  → factory.audio 的配音/音效指令
```

---

# 3. LangGraph 完整状态图（factory.novel）

## 3.1 State Schema

```python
class NovelState(TypedDict):
    # 任务标识
    run_id:          str
    volume_no:       int
    ch_no:           int

    # 各 skill 产物 ID
    outline_id:      str | None
    plot_id:         str | None
    chapter_id:      str | None
    screenplay_id:   str | None

    # 运行时数据
    prev_tail:       str          # 上章结尾
    knowledge_snapshot: dict
    qa_result:       dict | None
    retry_count:     int          # chapter 重试次数（上限 2）

    # 流程控制
    status:          str          # running | needs_human | done | failed
    human_feedback:  str | None   # 人在环返回的意见
```

## 3.2 完整图定义

```python
from langgraph.graph import StateGraph, END

def build_novel_graph():
    g = StateGraph(NovelState)

    g.add_node("outline",    skill_novel_outline.run)
    g.add_node("h_outline",  interrupt_for_review)    # 人在环：大纲审核
    g.add_node("plot",       skill_novel_plot.run)
    g.add_node("chapter",    skill_novel_chapter.run)
    g.add_node("dialogue",   skill_novel_dialogue.run)
    g.add_node("qa",         skill_qa_consistency.run)
    g.add_node("export",     skill_novel_export.run)
    g.add_node("screenplay", skill_novel_screenplay.run)  # 小说→多维剧本卡

    # 顺序边
    g.add_edge("outline",   "h_outline")
    g.add_edge("h_outline", "plot")
    g.add_edge("plot",      "chapter")
    g.add_edge("chapter",   "dialogue")
    g.add_edge("dialogue",  "qa")

    # QA 路由
    g.add_conditional_edges("qa", route_after_qa, {
        "pass":        "export",
        "retry":       "chapter",    # retry_count < 2
        "needs_human": END,          # retry 耗尽，置 needs_human
    })

    # export 后并行进行剧本转换（export 写 txt/epub，screenplay 写 beat cards）
    g.add_edge("export",     "screenplay")
    g.add_edge("screenplay", END)
    g.set_entry_point("outline")
    return g.compile()

def route_after_qa(state: NovelState):
    if state["qa_result"]["passed"]:
        return "pass"
    if state["retry_count"] < 2:
        return "retry"
    return "needs_human"
```

---

# 4. 人在环触发点（factory.novel）

| 节点 | 触发条件 | 审核人 | 可操作 |
|------|---------|--------|--------|
| `h_outline` | 每卷大纲生成后 | 剧情设计 | 批准 / 修改大纲 / 打回重生成 |
| QA `needs_human` | chapter 重试 2 次仍有 hard 冲突 | 剧情设计 | 手动修正冲突段落后 resume |
| screenplay 抽查 | 每卷首章 screenplay 生成后 | 剧情设计 + 美工 | 确认 beat 拆分粒度和构图指令是否合适 |
| 卷末复盘 | 全卷 30 章完成后 | 全员 | 重评角色量化分、检查 S/A 级分布 |

---

# 5. 渐进式实现建议（Phase 1 起步）

| 迭代 | 实现 | 跳过 |
|------|------|------|
| v0（立即可跑） | outline + chapter（合并 plot）+ qa（仅规则层）+ export(txt) | dialogue、plot 独立节点、screenplay |
| v1 | 拆出 plot 节点 + dialogue + QA LLM 兜底 | epub export、screenplay |
| v2 | + screenplay（beat 卡驱动视觉）+ 完整人在环 + epub | — |

> v0 只需 3 个节点就能跑出第一章。**先跑起来拿到真实数据，再补细节。**
