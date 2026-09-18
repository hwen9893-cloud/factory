# 长篇小说生产能力增强

本次改造沿用 `SimpleWorkflow`、`ChapterProductionPipeline`、现有 Agent 注册表、`BookRepository`、`SchemaStore`、`MemoryStore`、Provider、CLI 与 GUI。没有引入第二套调度器、记忆系统或数据库。

## 当前小说数据流分析

改造前的真实数据流是：

```text
Story Seed
→ WorldBuilder / Character / NovelArchitect / Outline / VolumePlanner
→ knowledge JSON + SchemaStore
→ MemoryRetriever（Canon、相关人物、线程、近章摘要、上章末尾）
→ ChapterPlanner（同时承担章节意图与场景拆分）
→ ChapterWriter
→ Continuity + Reviewer
→ Revision 循环
→ final.md
→ MemoryAgent 提取并直接调用 MemoryUpdater
→ ChapterRecord
```

`ChapterProductionPipeline` 是唯一单章编排器；`SimpleWorkflow` 只区分建书步骤和单章步骤。检查点保存在 `chapters/chNNN/pipeline.json`。CLI 与 GUI 都经 `FactoryService` 调用工作流。

可直接复用：Workflow、BaseAgent/注册表、Provider/ModelRegistry、BookRepository、SchemaStore、MemoryStore/MemoryRetriever、事件与 checkpoint、FactoryService 和 GUI 后端。

需要扩展：StorySchema/Memory 边界、ChapterPlan、章节规划、Continuity、Revision、MemoryAgent、单章流水线和 Service 入口。

新增且必要：框架解析/校验/预览、版本化 Story Bible/Story State 契约、ScenePlanner、确定性校验器、状态事务适配器。

不应修改职责：Provider、模型路由、Workflow 调度方式、GUI 后端架构、现有 JSON 项目布局。

原职责过宽：ChapterPlanner 同时产出意图与场景；Revision 同时承担内容和文风；MemoryAgent 既提取又直接落库。三者现已拆开，同时保留兼容入口。

## 最终数据流

```text
Markdown Framework
→ Parser → Normalizer → Schema/Reference Validator → Import Preview
→ StoryBibleRepository
→ Story Bible + Story State
→ MemoryRetriever（支持 ContextRequest / ContextBundle / token budget）
→ ChapterPlannerAgent → ChapterIntent
→ ScenePlannerAgent → ScenePlan[] → SceneCoverageValidator
→ ChapterWriterAgent → Draft
→ ContinuityAgent（确定性规则 + 语义检查）
→ ContentRevisionAgent → CorrectedDraft
→ StylePolisherAgent → FactDiff → FinalValidator
→ MemoryAgent → StoryStateDelta
→ AtomicFinalizer（final + record + state + snapshot + 旧存储投影）
```

## 分阶段结果

### Phase 1：数据契约

- 增加 Story Bible、Story State、State Delta、FactSource、Provenance、金手指/反派/主线/Hook/爽点/文风契约和稳定 ID。
- `schema_version=2`；所有新增字段有默认值，Pydantic 忽略旧项目未知字段。
- 旧 `StorySchema` 和 `StoryMemory` 不删除，通过 Repository 兼容加载。

### Phase 2：框架导入

- 增加确定性 Markdown Parser、可约束 Normalizer、Schema/引用校验、Preview、create/merge/replace 和来源追踪。
- 显式 ID 原样保留；无 ID 时确定性生成；相同内容重复导入幂等。
- Story Bible 同步投影到现有 world/characters/plot/outline 文件。

### Phase 3：规划

- ChapterPlanner 只产出 ChapterIntent；ScenePlanner 独立生成 ScenePlan。
- Writer 必须获得场景计划；旧 ChapterPlan 场景卡仍可兼容读取。
- 旧工作流同时请求 planner/writer 时会自动插入 scene planner。

### Phase 4：质量链

- Revision 保留为兼容 facade；新流程使用 ContentRevision 与 StylePolisher。
- FinalValidator 校验场景覆盖、禁止事项和润色前后受保护事实。
- Continuity 增加知识边界、金手指冷却、Hook/爽点冷却等确定性规则。

### Phase 5：状态事务

- MemoryAgent 只返回 StoryStateDelta，不直接持久化。
- Delta 校验版本并按 operation_id 幂等；状态带版本号。
- AtomicFinalizer 通过 staging、原子替换、备份与 manifest 一次提交正文、记录、状态和旧 Memory/Schema 投影；失败整体回滚。
- 每版状态写 snapshot，并支持 `get_snapshot()` 与 `rollback_to()`。

### Phase 6：CLI / GUI

- CLI：`factory framework validate|preview|import`。
- GUI：新增“框架导入”，上传 Markdown 后先显示校验和变更，再确认写入。
- GUI 仍只调用 FactoryService。

## 兼容与存储

旧项目首次访问 Story Bible/State 时从现有 knowledge/memory 文件补齐；不会要求一次性迁移。原有 Repository、JSON 和可选 SQLite Memory 后端继续可用。Qwen Provider 未改动。

新增文件主要位于：

```text
factory/framework/
factory/state/
factory/schema/contracts.py
factory/pipeline/quality.py
factory/pipeline/rules.py
factory/pipeline/validators.py
factory/agents/scene.py
factory/gui/framework.py
```

测试覆盖 Markdown 转 Schema、稳定 ID、引用错误、单实体合并、重复 Delta、版本冲突、事务回滚、润色事实变化、知识边界、金手指冷却、预算上下文和端到端导入生成。
