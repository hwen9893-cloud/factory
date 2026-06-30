# 61 - 数据契约与 Schema

> Version：v1.1　Last Update：2026-06
> Status：Active
> 依赖：`11-模块命名规范.md`、`12-术语与Skill规范.md`、`42-知识库设定规范.md`、`32-硬件与部署方案.md`、`43-factory.novel流水线规范.md`

---

# 1. 文档目的

把 `11` 的 ID 规范、`31` 的 lineage 约束落地为**实际数据库表结构与跨模块数据契约**，作为代码实现的唯一接口依据。

> 第一阶段用 **PostgreSQL 关系表**，不上 Neo4j（关系复杂度未到，见 `21` §2.4）。

---

# 2. ID 规范落地

## 2.1 实体 ID（三段式，源自 `11` §2.2）

```
{module}.{entity}.{id}
asset.character.0001        # 角色资产
asset.lora.0001-v3          # 该角色第 3 版 LoRA
knowledge.timeline.0042     # 时间线条目
knowledge.sect.0007         # 宗门设定条目
```

## 2.2 表前缀规约（源自 `11` §2.3）

| 模块 | 表前缀 |
|------|--------|
| `center.knowledge` | `center_knowledge_*` |
| `center.asset` | `center_asset_*` |
| `factory.novel` | `factory_novel_*` |
| `factory.visual` | `factory_visual_*` |

---

# 3. 核心表结构（PostgreSQL）

## 3.1 资产表 `center_asset_item`

| 字段 | 类型 | 说明 |
|------|------|------|
| `asset_id` | text PK | 三段式 ID |
| `type` | text | character/costume/prop/lora/voice/... |
| `name` | text | 人类可读名 |
| `current_version` | text | 当前版本号 |
| `storage_uri` | text | NAS/MinIO 路径 |
| `appearance_spec` | jsonb | 外观规格（见 §5） |
| `created_at` / `updated_at` | timestamptz | — |

## 3.2 知识表 `center_knowledge_item`

| 字段 | 类型 | 说明 |
|------|------|------|
| `knowledge_id` | text PK | 三段式 ID |
| `entity` | text | character/sect/artifact/place/realm/timeline/relation |
| `payload` | jsonb | 设定内容（各实体字段见 §3.2.1） |
| `embedding` | vector(1024) | 设定文本向量，用于语义检索（pgvector，对应 bge-m3 输出维度） |
| `created_at` / `updated_at` | timestamptz | — |

### 3.2.1 payload 各实体字段定义

**character（角色）**
```json
{
  "name":           "string",
  "aliases":        ["string"],
  "gender":         "string",
  "realm":          "knowledge.realm.ID（当前境界）",
  "sect":           "knowledge.sect.ID（所属宗门，可空）",
  "appearance":     "string（外貌描述，供 factory.visual 参考）",
  "personality":    "string（性格核心，供 dialogue skill 注入）",
  "voice_style":    "string（声线描述，见 44 §4）",
  "scores": {
    "A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0, "G": 0
  },
  "char_type":      "主角|反派|师长|道侣|配角",
  "weighted_total": 0.0,
  "core_motivation":"string（核心欲望/执念）",
  "taboo":          "string（禁忌/死穴，可空）",
  "status":         "alive|dead|unknown",
  "debut_chapter":  "integer"
}
```

**realm（境界体系）**
```json
{
  "system_name":  "string（如「修仙九境」）",
  "levels": [
    { "no": 1, "name": "练气期", "sub_levels": 9, "power_desc": "string" }
  ],
  "special_physiques": ["string"],
  "realm_jump_rules":  "string（越级战斗规则说明）"
}
```

**sect（宗门/势力）**
```json
{
  "name":         "string",
  "aliases":      ["string"],
  "tier":         "integer（势力等级 1–5）",
  "location":     "knowledge.place.ID",
  "leader":       "knowledge.character.ID",
  "stance":       "友方|敌方|中立|待定",
  "specialty":    "string（擅长功法/法器类型）",
  "members":      ["knowledge.character.ID"]
}
```

**artifact（法宝/功法）**
```json
{
  "name":         "string",
  "type":         "法宝|功法|丹药|阵法",
  "tier":         "integer（品阶）",
  "owner":        "knowledge.character.ID（可空）",
  "abilities":    ["string"],
  "restrictions": ["string（使用限制/代价）"],
  "origin":       "string（来历）"
}
```

**timeline（时间线条目）**
```json
{
  "event_name":   "string",
  "chapter_no":   "integer（发生章节）",
  "participants": ["knowledge.character.ID"],
  "location":     "knowledge.place.ID",
  "outcome":      "string（事件结果）",
  "caused_by":    ["knowledge.timeline.ID（前因，可空）"],
  "causes":       ["knowledge.timeline.ID（后果，可空）"]
}
```

**place（地点）**
```json
{
  "name":         "string",
  "parent":       "knowledge.place.ID（可空，上级区域）",
  "controller":   "knowledge.sect.ID（可空）",
  "danger_level": "integer（危险度 1–5）",
  "description":  "string"
}
```

## 3.3 关系表 `center_knowledge_relation`

| 字段 | 类型 | 说明 |
|------|------|------|
| `relation_id` | text PK | — |
| `from_id` | text FK | 角色 KnowledgeID |
| `to_id` | text FK | 角色 KnowledgeID |
| `rel_type` | text | 师门/宿敌/道侣/同伴（对接 `41` F 层） |
| `power_diff` | text | 强/平/弱 |
| `sentiment` | text | 正/负/矛盾 |

## 3.4 factory.novel 专属表

### factory_novel_run（生产任务）

| 字段 | 类型 | 说明 |
|------|------|------|
| `run_id` | uuid PK | 每次生产任务 ID |
| `volume_no` | integer | 卷号 |
| `ch_no` | integer | 章号（NULL 表示全卷任务） |
| `status` | text | running / needs_human / done / failed |
| `retry_count` | integer | QA 重试次数 |
| `created_at` / `updated_at` | timestamptz | — |

### factory_novel_outline（卷大纲）

| 字段 | 类型 | 说明 |
|------|------|------|
| `outline_id` | uuid PK | — |
| `run_id` | uuid FK | 关联任务 |
| `volume_no` | integer | — |
| `chapters` | jsonb | 章数组（见 `43` §2.1 Output Schema） |
| `approved` | boolean | 人在环是否已批准 |
| `human_feedback` | text | 审核意见（可空） |
| `lineage` | jsonb | — |
| `created_at` | timestamptz | — |

### factory_novel_plot（场景卡）

| 字段 | 类型 | 说明 |
|------|------|------|
| `plot_id` | uuid PK | — |
| `outline_id` | uuid FK | — |
| `ch_no` | integer | — |
| `scenes` | jsonb | 场景卡数组（见 `43` §2.2 Output Schema） |
| `lineage` | jsonb | — |
| `created_at` | timestamptz | — |

### factory_novel_chapter（章节正文）

| 字段 | 类型 | 说明 |
|------|------|------|
| `chapter_id` | uuid PK | — |
| `plot_id` | uuid FK | — |
| `ch_no` | integer | — |
| `title` | text | — |
| `body` | text | 正文（含 dialogue 润色后版本） |
| `word_count` | integer | — |
| `qa_passed` | boolean | 是否通过一致性校验 |
| `qa_conflicts` | jsonb | 冲突列表（可空） |
| `status` | text | draft / qa_passed / exported / screened |
| `lineage` | jsonb | — |
| `created_at` / `updated_at` | timestamptz | — |

### factory_novel_screenplay（多维剧本卡）

| 字段 | 类型 | 说明 |
|------|------|------|
| `screenplay_id` | uuid PK | — |
| `chapter_id` | uuid FK | 关联章节 |
| `plot_id` | uuid FK | 关联场景卡（保留场景对应关系） |
| `ch_no` | integer | 章号 |
| `beats` | jsonb | Beat Cards 数组（完整结构见 `43` §2.7 Output Schema） |
| `total_beats` | integer | 本章 beat 总数 |
| `est_duration_sec` | integer | 全章预估总时长（秒） |
| `style_ref` | text | 美术风格指令（可空） |
| `reviewed` | boolean | 是否经剧情+美工联合抽查 | 
| `lineage` | jsonb | 含 chapter_id / plot_id / skill / model |
| `created_at` | timestamptz | — |

> `beats` 字段 JSONB 结构与 `43` §2.7 Output Schema 严格对应，包含：
> `visual`（画面+色调+道具+特效）· `composition`（镜头·角度·运动·景深）·
> `characters`（每人的位置·动作·表情·情绪·视线）·
> `dialogue`（台词·语气·潜台词）· `inner_monologue`（内心独白·情绪基调）·
> `sound`（BGM 提示·音效·环境音）· `pacing` · `duration_est_sec` · `爽点`

---

# 4. lineage（血缘）与版本

## 4.1 lineage 表 `lineage_edge`

记录"每个产物由哪些输入生成"，满足 `22` 标准 #4（100% 可溯源）。

| 字段 | 类型 | 说明 |
|------|------|------|
| `output_id` | text | 产物 ID（asset/knowledge/章节） |
| `output_version` | text | 产物版本 |
| `input_ids` | text[] | 输入的 AssetID/KnowledgeID 列表 |
| `skill` | text | 生成它的 skill 名（如 `skill.visual.image_gen`） |
| `model` | text | 使用的模型后端（见 `33`） |
| `params` | jsonb | seed/prompt 模板/参数 |
| `created_at` | timestamptz | — |

## 4.2 版本与回滚

| 机制 | 说明 |
|------|------|
| 版本号 | `{id}-v{n}`，每次重生成递增 |
| 不可变 | 旧版本不删除，保留以支持回滚 |
| 回滚 | 将 `current_version` 指回历史版本即可 |

> 任意成品可回滚到任意中间版本（`22` 标准 #4）。

---

# 5. appearance spec 字段（跨模态契约）

供 `factory.visual` 确定性注入 prompt（与 `51` §3 同源），存 `center_asset_item.appearance_spec`：

```json
{
  "hair": "玄色长发束冠",
  "eyes": "金瞳",
  "outfit": "青色道袍+玄铁护腕",
  "marks": ["左眉断痕"],
  "signature_item": "古剑·噬魂",
  "build": "清瘦少年",
  "temperament": ["阴冷", "不羁"]
}
```

---

# 6. 跨模块数据流契约

```
factory.* 的 skill：
  read  : 查询 center（按 ID 取 payload / spec）
  generate : 产出新内容
  write : 写回 center + 追加 lineage_edge（必带 input_ids/skill/model/params）
```

铁律：
- factory 只能**引用 ID**，不得脱离 ID 重新生成同一资产（`11` §2.2）。
- 每次写回**必须**追加 lineage，否则视为不合规产物（CI/评测拦截，见 `72`）。
