# AI Cultivation Studio — 文档总览（INDEX）

> 从网文到动漫的 Agent Skills 工厂｜策略文档体系
> Version：v1.0　Last Update：2026-06
> 平台基线：**Mac Studio（本地）+ 云 GPU（突发）**｜基座：**`center.model` 多后端（默认见 `docs/33-模型选型策略.md`）**
> 团队基线：**3 人 —— 剧情设计 / 美工设计 / 代码实现**

---

# 1. 命名规范（所有文档统一遵循）

## 1.1 文件名格式

```
NN-中文短名.md
```

- `NN`：两位数字前缀，按**层级分段**（见 §1.2）。
- 中文短名：精简、不含括号注记（历史版本注记写进文首元信息，不写进文件名）。
- 一个层级内按依赖/阅读顺序递增编号；预留尾号（如 49）给"附录/降级文档"。

## 1.2 编号规则

**格式：`XY`，X = 层级，Y = 层内序号（9 固定保留给附录/降级文档）**

| X（十位） | 层级 | 负责人 | 含义 |
|-----------|------|--------|------|
| 1x | 权威层 | 全员 | 命名、术语等所有文档必须引用的根规范 |
| 2x | 战略层 | 全员 | 路线、成功标准、预算（决定方向） |
| 3x | 架构层 | 代码 | 系统/硬件/模型架构（决定结构） |
| 4x | 剧情执行层 | 剧情 | 角色量化、知识库设定 |
| 5x | 美工执行层 | 美工 | 一致性 Playbook 与预研 |
| 6x | 代码执行层 | 代码 | 数据契约、Skill 实现 |
| 7x | 协作与横切层 | 全员 | 协作 SOP、评测工程 |

## 1.3 文首元信息（每份文档统一首部）

```
> Version：vX.Y　Last Update：YYYY-MM
> Status：Draft / Active / Authoritative
> 依赖：引用到的上游文档（以 Canonical ID 为准）
```

## 1.4 模块 / 实体命名

一律以 `docs/11-模块命名规范.md` 的 Canonical ID 为唯一权威：
`{type}.{name}`（如 `factory.novel`）、实体三段式 `{module}.{entity}.{id}`（如 `asset.character.0001`）。

---

# 2. 文档地图

## 权威层（1x）
| 文件 | 状态 | 说明 |
|------|------|------|
| `docs/11-模块命名规范.md` | Authoritative | 唯一权威模块清单与命名规范 |
| `docs/12-术语与Skill规范.md` | Active | 定义 skill / factory / center / orchestrator 关系 |

## 战略层（2x）
| 文件 | 状态 | 说明 |
|------|------|------|
| `docs/21-精益路线.md` | Active | 3 人版 Market-First 路线（Phase 0–3） |
| `docs/22-成功标准与里程碑.md` | Active | 量化验收标准 + M1–M7 + M3.5 |
| `docs/23-预算与资源约束.md` | Active | Capex / Opex 结构与花钱节奏 |

## 架构层（3x）
| 文件 | 状态 | 说明 |
|------|------|------|
| `docs/31-系统架构.md` | Active | 六层架构（分层 Local First） |
| `docs/32-硬件与部署方案.md` | Active | Mac Studio + 云 GPU 突发部署 |
| `docs/33-模型选型策略.md` | Active | Llama3 vs 中文模型，多后端封装 |
| `docs/34-center.model接口规范.md` | Active | 统一模型接口、profile 配置、重试策略 |

## 剧情执行层（4x）
| 文件 | 状态 | 说明 |
|------|------|------|
| `docs/41-修仙爽文角色量化系统.md` | Active（主文档） | 生产用角色量化系统 v2 |
| `docs/42-知识库设定规范.md` | Active | `center.knowledge` 实体与冲突检查 |
| `docs/43-factory.novel流水线规范.md` | Active | 各 skill I/O Schema + LangGraph 图 |
| `docs/44-Prompt库.md` | Active | 修仙爽文 system prompt 模板库 |
| `docs/45-合规与内容安全.md` | Active | AIGC 标识、内容安全红线、合规 skill |
| `docs/49-人物量化方法论.md` | Reference（附录） | 通用方法论框架 |

## 美工执行层（5x）
| 文件 | 状态 | 说明 |
|------|------|------|
| `docs/51-一致性Playbook.md` | Active | Mac/云分工的一致性落地手册 |
| `docs/52-一致性技术预研方案.md` | Active | 四维度预研与 M3.5 关卡 |

## 代码执行层（6x）
| 文件 | 状态 | 说明 |
|------|------|------|
| `docs/61-数据契约与Schema.md` | Active | AssetID/KnowledgeID/lineage + factory_novel_* 表 |
| `docs/62-AgentSkills实现规范.md` | Active | Skill 代码骨架与 LangGraph 注册 |

## 协作与横切层（7x）
| 文件 | 状态 | 说明 |
|------|------|------|
| `docs/71-三人协作SOP.md` | Active | owning 边界 / RACI / 交接契约 |
| `docs/72-评测工程EvalHarness.md` | Active | 把验收数字变成可复跑脚本 |

---

# 3. 阅读顺序建议

- **新成员入门**：`README` → `11` → `12` → `21` → `31`
- **剧情**：`21` → `41` → `42` → `43` → `44` →（方法论）`49`
- **美工**：`21` → `51` → `52` → `33`（视觉模型）
- **代码**：`31` → `32` → `33` → `34` → `61` → `62` → `72`
- **决策复盘**：`22` → `72` → `21`

---

# 4. 三人 owning 速查

| 人 | 主 owning 模块 | 主文档 |
|----|--------------|--------|
| 剧情设计 | `factory.novel` · `center.knowledge` | `41` · `42` · `43` · `44` |
| 美工设计 | `factory.visual` · `center.asset` · 一致性 | `51` · `52` |
| 代码实现 | `infra` · `orchestrator` · `center.*` · skills | `31` · `32` · `33` · `34` · `61` · `62` |
