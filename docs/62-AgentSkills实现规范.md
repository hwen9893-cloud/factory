# 62 - Agent Skills 实现规范

> Version：v1.1　Last Update：2026-06
> Status：Active
> 依赖：`12-术语与Skill规范.md`、`31-系统架构.md`、`34-center.model接口规范.md`、`43-factory.novel流水线规范.md`、`61-数据契约与Schema.md`、`72-评测工程EvalHarness.md`

---

# 1. 文档目的

把 `12-术语与Skill规范.md` 的 skill 概念落到**代码骨架、接口实现与 LangGraph 注册**，作为代码实现的执行手册。

---

# 2. Skill 目录结构

```
backend/
  skills/
    novel/
      outline.py        # skill.novel.outline
      plot.py           # skill.novel.plot
      chapter.py        # skill.novel.chapter
      dialogue.py       # skill.novel.dialogue
      export.py         # skill.novel.export
      screenplay.py     # skill.novel.screenplay（小说→多维剧本卡，驱动视觉/动画）
    visual/
      charactersheet.py
      image_gen.py
      lora_train.py     # 云 GPU 任务
    qa/
      consistency.py    # 横切 skill.qa.consistency
    base.py             # Skill 基类与契约
  center/
    model/
      client.py         # ModelClient 统一接口（见 34）
      profiles.yaml     # profile 配置
```

> 目录名对齐 `11` 的 factory 名；文件名对齐 skill 的 `{action}`。

---

# 3. Skill 标准 I/O 实现

每个 skill 实现统一基类契约（伪代码）：

```python
class Skill:
    name: str                      # "skill.novel.outline"
    input_schema: dict             # JSON Schema
    output_schema: dict            # JSON Schema（含 lineage 字段）

    def run(self, state: dict) -> dict:
        inputs = self.validate_input(state)      # 校验 + 解析引用 ID
        refs = self.fetch_from_center(inputs)    # 按 ID 查 center（只引用，不重生成）
        result = self.generate(refs)             # 调 center.model 等工具
        self.write_back(result)                  # 写回 center + 追加 lineage_edge
        return self.validate_output(result)
```

- **input/output 必须经 schema 校验**，不合规即 fail-fast。
- 写回必带 lineage（`61` §4），否则评测拦截。

---

# 4. LangGraph 节点注册

```python
graph.add_node("outline", skill_novel_outline.run)
graph.add_node("chapter", skill_novel_chapter.run)
graph.add_node("qa",      skill_qa_consistency.run)

graph.add_edge("outline", "chapter")
graph.add_conditional_edges("qa", route_by_qa)   # 通过→export / 不通过→chapter(回写)
```

- 一个节点 = 一个 skill.run（`12` §3）。
- 节点间只传递结构化 state，不传隐式上下文。
- 任一节点可替换为同契约 skill（Replaceable，`31` §11⑥）。

---

# 5. 人在环节点（interrupt）

关键节点暂停等人工放行（触发点见 `71-三人协作SOP.md`）：

```python
graph.add_node("human_review", interrupt_for_review)
# 暂停 → 人工在 Dashboard 审核 → resume 携带审核结果
```

| 人在环点 | 谁审 | 放行条件 |
|---------|------|---------|
| 大纲/设定评审 | 剧情 | 设定无冲突 |
| 立绘/角色定妆评审 | 美工 | 风格/一致达标 |
| M3.5 一致性关卡 | 美工+代码 | 四维度达标（`52` §4） |

---

# 6. 标准化横切要素

| 要素 | 实现要求 |
|------|----------|
| Prompt | 模板与变量分离；设定由 spec 注入，禁硬编码（`51` §3） |
| Memory | 运行态短期记忆，不替代 center 持久化 |
| Log | 结构化日志，含 skill 名/输入 ID/模型/耗时 |
| Tools | 经 `center.model` 统一接口调模型（`34` §2，`33` §1） |
| Eval hook | 暴露评测钩子，对接 `72` |

---

# 7. 五大 Factory 的 Skill 拆解清单

## 7.1 factory.novel
`skill.novel.outline` → `skill.novel.plot` → `skill.novel.chapter` → `skill.novel.dialogue` → `skill.qa.consistency` → `skill.novel.export` → `skill.novel.screenplay`

> 各 skill 完整 I/O Schema、LangGraph 图定义、人在环触发点见 `43-factory.novel流水线规范.md`。
> Prompt 模板见 `44-Prompt库.md`。
>
> `skill.novel.screenplay` 将章节正文转换为**多维剧本卡（Beat Cards）**，输出供 `factory.visual` 生图和 `factory.animation` 分镜使用，是 `factory.novel` → 视觉/动画 pipeline 的桥接节点。

## 7.2 factory.visual
`skill.visual.reference` → `skill.visual.charactersheet` → `skill.visual.image_gen` → `skill.visual.lora_train`（云） → `skill.visual.register`（写 `center.asset`）

## 7.3 factory.animation
`skill.anim.storyboard` → `skill.anim.camera` → `skill.anim.keyframe` → `skill.anim.video`（云） → `skill.anim.fx` → `skill.anim.render`

## 7.4 factory.audio
`skill.audio.tts` → `skill.audio.voice_clone` → `skill.audio.music` → `skill.audio.foley` → `skill.audio.subtitle`

## 7.5 factory.publishing
`skill.publish.format` → `skill.publish.adapt` → `skill.publish.push` → `skill.publish.report`（回传 `center.operation`）

---

# 8. 渐进式实现策略

| 阶段 | skill 实现方式 |
|------|---------------|
| Phase 0 | 现成工具 + 人工，**不写 skill 代码**（见 `21` §1） |
| Phase 1 | 选定形式的 skill 落代码（如有声书：novel + audio 链） |
| Phase 2 | 视觉/视频 skill（多数为云 GPU 任务）+ 完整 LangGraph 编排 |

> 半手工 skill 允许先以脚本实现，量大后再升级为全自动节点。

---

# 9. 编排层失败语义与错误处理契约

> `31` §5 提到 Celery/Redis 任务队列，`22` 标准 #5 要求成功率 ≥ 95%。本节定义支撑该 SLA 的失败处理规范。

## 9.1 失败类型分级

| 级别 | 类型 | 例子 | 处理方式 |
|------|------|------|---------|
| **Transient**（瞬时） | 网络/模型超时，可重试 | Ollama 响应超时、云 GPU 启动延迟 | 自动重试（见 `34` §4） |
| **Soft**（软失败） | 输出不合格，需回退 | QA 冲突、合规未通过 | 路由回上游节点（`43` §3.2） |
| **Hard**（硬失败） | 无法自动恢复 | schema 校验失败、磁盘满、DB 连接断 | 任务状态置 `failed`，触发告警，人工介入 |
| **Poison**（毒消息） | 任务反复触发同一异常 | 某 prompt 组合必触发 OOM | 移入死信队列，告警，人工排查后删除或修复 |

## 9.2 重试策略

```python
RETRY_POLICY = {
    "max_retries": 3,
    "backoff": "exponential",  # 1s → 2s → 4s
    "retryable_exceptions": [
        "ModelUnavailableError",   # center.model 超时/fallback 后仍失败
        "ConnectionError",
        "TimeoutError",
    ],
    "non_retryable": [
        "SchemaValidationError",   # 输入/输出不合规 → 直接 Hard fail
        "ComplianceHardError",     # 合规 Hard 问题 → 直接人工
    ],
}
```

## 9.3 任务状态机

```
pending → running → done
                 ↘ failed（hard / poison）
                 ↘ needs_human（QA/合规 hard 冲突，重试耗尽）
failed → [人工 fix] → retrying → done | failed
```

任务状态持久化在 `factory_novel_run.status` 字段（见 `61` §3.4）；所有状态转换写日志。

## 9.4 幂等性要求

每个 skill 的 `run()` 必须**幂等**：用相同的 `run_id + 输入` 重跑不产生副作用：

- 写 DB 前先 `SELECT`：若已有同 `run_id` 的记录，跳过写入直接返回已有结果
- 文件/资产生成：若 AssetID 已存在且版本匹配，直接返回已有 AssetID
- lineage 追加：幂等（同 `output_id + skill` 的 edge 若已存在则跳过）

## 9.5 死信队列（Celery Dead Letter Queue）

```python
# celery 配置（infra/celery_config.py）
task_acks_late = True          # 任务完成后才确认，防崩溃丢失
task_reject_on_worker_lost = True
CELERY_QUEUES = {
    "main":       Queue("main"),
    "dead_letter":Queue("dead_letter"),   # 毒消息归宿
}

# 超过 max_retries 后路由到死信队列
task_annotations = {
    "*": {"on_failure": route_to_dead_letter}
}
```

死信队列每日告警汇总，代码实现人每日晨检一次。

## 9.6 全局超时保护

| 任务类型 | 软超时（告警） | 硬超时（强杀） |
|---------|-------------|-------------|
| LLM 推理（本地） | 3 min | 5 min |
| LLM 推理（云 fallback） | 5 min | 10 min |
| 云 GPU 任务（图/视频） | 30 min | 60 min |
| 数据库操作 | 30 s | 60 s |
| 全流水线（chapter→screenplay） | 20 min | 30 min |
