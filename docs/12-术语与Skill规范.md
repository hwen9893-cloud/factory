# 12 - 术语与 Skill 规范

> Version：v1.0　Last Update：2026-06
> Status：Active（权威层，所有执行层文档须引用本规范）
> 依赖：`11-模块命名规范.md`

---

# 1. 文档目的

`11-模块命名规范.md` 定义了 `factory` / `center` / `service` / `infra` 四类**模块**。但本项目的目标是"**Agent Skills 工厂**"，引入了 `skill` 这一更细的粒度。本文档定义 skill 与既有概念的关系，消除术语漂移。

---

# 2. 核心术语定义

| 术语 | 定义 | 关键判据 | 例子 |
|------|------|----------|------|
| **Skill** | 最小可复用、可独立评测的能力单元，有明确 input→output 契约 | 单一职责、可单测、可被多个 factory 复用 | `skill.novel.outline` |
| **Factory** | 若干 skill 按有序阶段组合成的一条生产流水线 | 有 input→output，被"运行/执行" | `factory.novel` |
| **Center** | 被引用的持久化共享状态，不含 skill | 被"查询/读写"，不被"运行" | `center.knowledge` |
| **Orchestrator** | 调度 skill / factory 的 LangGraph 编排层 | 全局任务调度，节点可替换 | `orchestrator` |
| **Service** | 横切能力，被多个 factory 调用 | 跨模块、无独立产物 | `center.qa`（横切） |

> 一句话关系：**Orchestrator 调度 → Factory 是 skill 的有序组合 → Skill 读写 Center。**

---

# 3. Skill 与 LangGraph 节点的映射

```
LangGraph Graph (= 一个 factory 的流水线)
   ├─ Node A  → skill.novel.outline
   ├─ Node B  → skill.novel.chapter
   ├─ Node C  → skill.qa.consistency   (横切 service skill)
   └─ Node D  → skill.novel.export
```

- **一个 LangGraph 节点 = 一次 skill 调用**。
- 节点之间只传递**结构化状态**（见 §5），不传递隐式上下文。
- 任一节点可替换为同契约的另一个 skill 实现（呼应架构原则 ⑥ Replaceable）。

---

# 4. Skill 命名规范

```
skill.{factory}.{action}
```

| 示例 | 含义 |
|------|------|
| `skill.novel.outline` | 小说工厂的"生成大纲"技能 |
| `skill.novel.chapter` | 生成章节正文 |
| `skill.visual.charactersheet` | 生成角色定妆图 |
| `skill.visual.lora_train` | 训练角色 LoRA（云 GPU） |
| `skill.audio.tts` | 文本转语音 |
| `skill.qa.consistency` | 设定一致性校验（横切） |
| `skill.publish.adapt` | 多平台格式适配 |

> `{factory}` 段对齐 `11` 的 factory 名；横切 skill 用 `qa`。Skill 名在代码、配置、日志、评测中必须**字面一致**。

---

# 5. Skill 标准接口

每个 skill 统一具备以下契约（落地细节见 `62-AgentSkills实现规范.md`）：

| 要素 | 说明 |
|------|------|
| **input schema** | 结构化输入，含引用的 `AssetID` / `KnowledgeID` |
| **output schema** | 结构化输出，写回 center 时附带 `lineage` |
| **prompt** | 模板与变量分离，禁止把设定硬编码进 prompt |
| **tools** | 可调用的工具集（模型、检索、外部 API） |
| **memory** | 运行态记忆（短期），不替代 center 的持久化 |
| **log** | 标准化日志，便于评测与回溯 |
| **eval hook** | 评测钩子，对接 `72-评测工程EvalHarness.md` |

铁律（呼应 `11` §2.2）：skill **只能引用 ID**，不得脱离 ID 重新生成同一资产。

---

# 6. Skill 组合规则

| 组合方式 | 用途 | 编排表达 |
|---------|------|----------|
| 串行 | 大纲→章节→审校 | LangGraph 顺序边 |
| 并行 | 同时生成多角色立绘 | LangGraph 并行分支 |
| 条件分支 | QA 通过→继续 / 不通过→回退 | LangGraph 条件边 |
| 人在环 | 关键节点暂停等人工放行 | interrupt 节点（见 `71-三人协作SOP.md`） |
| 循环 | 审校未过则重写（限次数） | LangGraph 带计数的回边 |

---

# 7. 五大 Factory 的 Skill 拆解（索引）

| Factory | 内部 skill 序列 | 详细拆解 |
|---------|----------------|----------|
| `factory.novel` | outline → plot → chapter → dialogue → qa → export → **screenplay** | `62` §7.1 |
| `factory.visual` | reference → charactersheet → image_gen → lora_train → register | `62` §7.2 |
| `factory.animation` | storyboard → camera → keyframe → video → fx → render | `62` §7.3 |
| `factory.audio` | tts → voice_clone → music → foley → subtitle | `62` §7.4 |
| `factory.publishing` | format → adapt → push → report | `62` §7.5 |

> Phase 0/1 阶段，部分 skill 允许"半手工"实现（脚本 + 人工），量大后再升级为全自动节点（见 `21-精益路线.md`）。
