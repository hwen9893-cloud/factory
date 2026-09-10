# Novel Factory

单机 Python 工具：用在线 LLM API 规划、写作、审稿、改稿长篇网文。

当前是可运行骨架。默认 `provider: mock`，不需要 API key，也不打真实模型。

`docs/` 是早期策略稿，不参与运行。

## 目录

1. [项目是什么](#1-项目是什么)
2. [设计理念](#2-设计理念)
3. [架构图](#3-架构图)
4. [项目目录](#4-项目目录)
5. [安装](#5-安装)
6. [环境变量](#6-环境变量)
7. [模型配置](#7-模型配置)
8. [创建小说](#8-创建小说)
9. [生成章节](#9-生成章节)
10. [Agent 工作流](#10-agent-工作流)
11. [Story Memory](#11-story-memory)
12. [数据保存位置](#12-数据保存位置)
13. [如何添加新 Agent](#13-如何添加新-agent)
14. [如何添加新模型 Provider](#14-如何添加新模型-provider)
15. [如何添加新 Prompt](#15-如何添加新-prompt)
16. [测试](#16-测试)
17. [Roadmap](#17-roadmap)

---

## 1. 项目是什么

Novel Factory 把一本长篇拆成固定步骤，每步一个 Agent：

- 开书：世界观 → 人物 → 故事骨架 → 总纲 → 分卷计划
- 单章：本章任务 → 正文 → 连续性检查 → 审稿 → 有限次改稿 → 写入 memory

输入是故事种子和 YAML 配置。输出是 `data/books/{book_id}/` 下的 JSON / Markdown 文件。

入口：

```bash
factory --help
python -m factory --help
```

不包含：RAG、向量库、Web UI、Agent 互调、LangGraph、动画/视觉管线。

---

## 2. 设计理念

| 规则 | 含义 |
|------|------|
| Agent 互不调用 | 只有 `SimpleWorkflow` / `ChapterProductionPipeline` 排序。Agent 只读 `Runtime`。 |
| 业务代码不 import 厂商 SDK | Agent 只调 `ModelClient`。OpenAI / Anthropic / Gemini SDK 关在 `factory/models/providers.py`。 |
| Prompt 是 Markdown 文件 | `factory/prompts/*.md`。占位符 `{{var}}`，不用 Jinja2。 |
| 模型名不写进 Python | 写在 YAML 的 `models.*`。密钥只在 `.env`。 |
| 不把全书正文塞进模型 | `MemoryRetriever` 只拼 canon、相关人物、相关伏笔、本卷切片、本章任务、近章摘要、上章文末。 |
| 一步一件事 | Writer 只写正文。Reviewer 只评估。Revision 只改稿。Continuity 只查设定。Memory 只归档。 |

配置优先级（后者覆盖前者）：

```text
config/default.yaml  <  项目 YAML  <  环境变量  <  CLI
```

项目 YAML 任选其一：`--config path.yaml`、`FACTORY_CONFIG`、仓库根目录 `factory.yaml`、`config/local.yaml`。

---

## 3. 架构图

```text
CLI (typer)
  factory init | architect | continue | write | review | ...
        │
        ▼
load_settings()          default.yaml < project < env < CLI
        │
        ▼
SimpleWorkflow(settings, book_id)
  BookRepository   PromptManager   ModelClient   StoryContext
  MemoryStore      MemoryRetriever MemoryUpdater UsageStore
        │
        ├── setup agents（AGENT_CLASSES）
        │     world_builder → character → novel_architect
        │     → outline → volume_planner
        │
        └── ChapterProductionPipeline
              load context → retrieve memory
              → chapter_planner → chapter_writer
              → continuity → reviewer → decision
                    ├─ pass → save
                    └─ fail → revision → re-review（≤ max_revision_rounds）
              → memory_update → persist
        │
        ▼
BaseAgent.ask_json / ask_text
  PromptManager.render(name.md)
  ModelClient.generate[_structured]
  Provider.complete          mock | openai | openrouter | anthropic | gemini
        │
        ▼
落盘: BookRepository + SchemaStore + MemoryStore
用量: data/books/usage.sqlite（元数据，无正文、无 API key）
```

```mermaid
flowchart TD
  CLI[factory CLI] --> Settings[load_settings]
  Settings --> WF[SimpleWorkflow]
  WF --> Setup[setup agents]
  WF --> Pipe[ChapterProductionPipeline]
  Setup --> Agent[BaseAgent]
  Pipe --> Agent
  Agent --> PM[PromptManager]
  Agent --> MC[ModelClient]
  MC --> P[Provider]
  Agent --> Repo[BookRepository]
  Pipe --> Mem[MemoryRetriever / MemoryUpdater]
  Mem --> Store[MemoryStore json or sqlite]
```

---

## 4. 项目目录

```text
.
├── config/
│   └── default.yaml          # 出厂配置（mock）
├── data/books/               # 书库，与代码分离
│   ├── usage.sqlite          # 模型调用统计
│   └── {book_id}/            # 见第 12 节
├── docs/                     # 策略文档，不参与运行
├── factory/                  # Python 包
│   ├── cli.py
│   ├── settings.py
│   ├── workflow.py
│   ├── context.py
│   ├── agents/               # BaseAgent 子类；互不 import
│   ├── models/               # ModelClient + providers + usage
│   ├── prompts/              # Markdown 模板 + PromptManager
│   ├── pipeline/             # 单章流水线与 Pydantic 契约
│   ├── memory/               # 分层记忆
│   ├── schema/               # 人物 / 世界 / 情节线 Schema
│   └── storage/              # BookRepository
├── tests/
├── .env.example
└── pyproject.toml
```

---

## 5. 安装

需要 Python 3.11+。

```bash
cd factory          # 本仓库根目录（含 pyproject.toml）
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env

# 离线冒烟：开书 + 写一章（mock，不打真实 API）
factory demo --out /tmp/factory-demo
```

离线 mock 到此即可。要接真实 API：

```bash
pip install -e ".[models]"
```

然后在 `.env` 填对应 key，并在 YAML 里改 `models.*.provider` / `models.*.model`。

跑测试：

```bash
pip install -e ".[test]"
```

---

## 6. 环境变量

复制 `.env.example` 为 `.env`。不要把 key 写进 YAML。

| 变量 | 作用 |
|------|------|
| `OPENAI_API_KEY` | OpenAI |
| `OPENROUTER_API_KEY` | OpenRouter |
| `ANTHROPIC_API_KEY` | Anthropic |
| `GEMINI_API_KEY` | Gemini（空则尝试 `GOOGLE_API_KEY`） |
| `FACTORY_PROVIDER` | 覆盖**所有** profile 的 provider。开发时保持 `mock` |
| `FACTORY_BOOK` | 默认书 id |
| `FACTORY_DATA_DIR` | 书库目录，默认 `data/books` |
| `FACTORY_CONFIG` | 项目 YAML 路径 |
| `FACTORY_LANGUAGE` | `project.language` |
| `FACTORY_CHAPTER_TARGET_WORDS` | 目标字数 |
| `FACTORY_MAX_REVISION_ROUNDS` | 改稿轮次上限 |
| `FACTORY_STORAGE_BACKEND` | `json` 或 `sqlite`（memory 后端） |
| `FACTORY_RECENT_CHAPTERS` | 近章条数 |
| `FACTORY_MODEL_ARCHITECT` 等 | 覆盖对应槽位的 **model id**，不是写进 Python |

CLI 高于环境变量：

```bash
factory --provider mock continue
factory --config ./factory.yaml status
```

`--book` / `-b` 只覆盖当前命令的书，不改 YAML。

---

## 7. 模型配置

四个命名槽位，Agent 通过 `model = "architect"|"planner"|"writer"|"reviewer"` 选用。

| 槽位 | Agent |
|------|--------|
| `architect` | `world_builder`, `character`, `novel_architect`（缺省回退 `planner`） |
| `planner` | `outline`, `volume_planner`, `chapter_planner` |
| `writer` | `chapter_writer`, `revision` |
| `reviewer` | `continuity`, `reviewer`, `memory` |

出厂 `config/default.yaml` 全是 mock。接真实模型时新建 `factory.yaml`（不要改 Python）：

```yaml
project:
  language: zh-CN
  book: my_novel

generation:
  chapter_target_words: 5000
  max_revision_rounds: 2

models:
  architect:
    provider: openrouter
    model: anthropic/claude-sonnet-4
    temperature: 0.45
  planner:
    provider: openai
    model: gpt-4o-mini
    temperature: 0.3
  writer:
    provider: anthropic
    model: claude-sonnet-4
    temperature: 0.8
  reviewer:
    provider: openai
    model: gpt-4o-mini
    temperature: 0.2

memory:
  recent_chapters: 3

storage:
  backend: json          # json | sqlite
  data_dir: data/books

# 可选：USD / 1M tokens，供 factory stats 估费
# pricing:
#   gpt-4o-mini:
#     input: 0.15
#     output: 0.60
```

已实现的 provider 名：`mock`、`openai`、`openai_compat`、`openrouter`、`anthropic`、`gemini`。

`api_key_env` 可省略，按 provider 使用上表默认环境变量名。

---

## 8. 创建小说

```bash
factory init my_novel \
  --title "残灵古剑" \
  --genre 修仙爽文 \
  --style "克制、短句、先抑后扬" \
  --seed "灵根残缺少年在宗门试炼中被逼入绝境，借旧伤中残留的古剑灵息反击。"
```

这会创建 `data/books/my_novel/`，并把该书写成 `.current`。

然后跑开书四步（世界、人物、骨架、总纲）：

```bash
factory architect --book my_novel
```

分卷：

```bash
factory plan-volume 1 --book my_novel
```

查看进度：

```bash
factory status
factory character list
factory plot list
```

书的解析顺序：`--book` → `FACTORY_BOOK` → `data/books/.current` → `project.book`。

---

## 9. 生成章节

一条命令走完整章流水线（缺分卷计划会先 `plan-volume`）：

```bash
factory continue
```

它找下一章还没有 `final.md` 的大纲章节。失败中断后，若 `pipeline.json` 状态是 `failed` / `running`，再次 `continue` 会从断点恢复。

拆开跑：

```bash
factory plan-chapter 1
factory write 1
factory review 1          # continuity + reviewer，不改稿
factory revise 1          # 只按最近审稿改一稿
```

其它：

```bash
factory memory show
factory stats             # 今日调用次数 / tokens / 估费 / 按 agent、model
factory stats --book my_novel
factory demo --out /tmp/factory-demo   # 离线 mock 冒烟
```

`factory stats` 读 `data/books/usage.sqlite`，不要求书已存在。

---

## 10. Agent 工作流

### Setup（`factory architect` + `plan-volume`）

```text
world_builder → character → novel_architect → outline → volume_planner
```

Workflow 按名字从 `AGENT_CLASSES` 取出类，依次 `run(state)`。Agent 之间没有函数调用。

### Chapter（`factory continue`）

```text
load_story_context
→ retrieve_relevant_memory
→ chapter_planner
→ chapter_writer
→ continuity_check
→ quality_review
→ decision
     ├─ pass → save
     └─ fail → revision → 再 continuity + review
               （次数 ≤ generation.max_revision_rounds，默认 2）
→ memory_update
→ persist
```

中间结果在 `chapters/chXXX/pipeline.json`。契约类型在 `factory/pipeline/models.py`：`ChapterPlan`、`ChapterDraft`、`ContinuityReport`、`ReviewResult`、`RevisionRequest`、`ChapterRecord`。

每步怎么调模型：

```text
BaseAgent.ask_json / ask_text
  → PromptManager.render(prompt_name)
  → ModelClient.generate[_structured](profile=self.model)
  → Provider.complete
```

---

## 11. Story Memory

写章节时不会加载历史正文全文。

检索包（`MemoryRetriever.for_writer`）：

- Level 1 Canon：世界摘要、规则、主角、永久事实
- Level 2 Entities：本章相关人物当前状态（有人数上限）
- Level 3 Plot：相关未收束伏笔、当前冲突
- Level 4 近章：最近 N 章摘要 + 上章文末 `prev_tail_chars` 字

章后：`MemoryAgent` 抽出结构化记录 → `MemoryUpdater.merge` → `MemoryStore` 落盘。

存储：

- 默认 JSON：`memory/canon.json`、`entities.json`、`plot.json`、`chapters.jsonl`
- `storage.backend: sqlite` 时同一套接口换 SQLite 文件

`factory memory show` 打印冲突、事实、开放线程、近章摘要。

---

## 12. 数据保存位置

根目录：`storage.data_dir`（默认 `data/books`）。

```text
data/books/
  .current
  usage.sqlite
  {book_id}/
    meta.json
    architecture.json
    outline.json
    volumes/v001/plan.json
    knowledge/
      world.json
      characters.json
      plot.json
      timeline.json
    chapters/ch001/
      plan.json
      draft.md
      continuity.json
      review.json
      final.md
      pipeline.json
      record.json
    memory/
      canon.json
      entities.json
      plot.json
      chapters.jsonl
      summaries.jsonl
```

书的正文、大纲、设定都在这里。代码仓库不提交章节产物（见 `.gitignore`）。

---

## 13. 如何添加新 Agent

1. 在 `factory/agents/` 新增类，继承 `BaseAgent`。
2. 设置 `name`、`model`（四个槽位之一）、`prompt_name`、`required_outputs`；JSON 步再设 `output_schema`。
3. 实现 `execute(self, state) -> dict`。只通过 `self.ask_json` / `self.ask_text` 调模型，不要 import 其它 Agent，不要 import 厂商 SDK。
4. 在 `factory/agents/__init__.py` 的 `AGENT_CLASSES` 注册。若属于单章流水线，同时加入 `CHAPTER_AGENTS`。
5. 需要进默认顺序时，改 `config/default.yaml` 的 `workflow` / `workflows.*`。
6. 补对应 `factory/prompts/{prompt_name}.md`（见第 15 节）。
7. 加一个离线测试：用 `MockModelProvider`，不要打真实 API。

最小骨架：

```python
class MyAgent(BaseAgent):
    name = "my_agent"
    model = "planner"
    prompt_name = "my_agent"
    required_outputs = ("result",)
    output_schema = {"type": "object"}

    def execute(self, state: dict) -> dict:
        payload = self.ask_json(purpose="my_agent")
        return {"result": payload}
```

---

## 14. 如何添加新模型 Provider

SDK 只能出现在 `factory/models/providers.py`。

1. 继承 `Provider`，实现 `complete(messages, *, model, config, json_mode) -> GenerationResult`。超时、429、5xx 抛 `RetryableError`，其它抛 `ProviderError`。不要在 Provider 里重试（`ModelClient` 会重试）。
2. 从环境变量读 key，不要把 key 写入 `GenerationResult` 或 usage 日志。
3. 在 `build_provider()` 按 `profile.provider` 分支构造。
4. 如需默认 key 名 / base URL，写入 `factory/models/types.py` 的 `DEFAULT_KEY_ENV`、`DEFAULT_BASE_URL`。
5. YAML 里把某个槽位的 `provider` 改成新名字。
6. 测试用 `MockModelProvider` 或假 key；单元测试禁止真实 HTTP。

`complete` 必须填 `text`、`model`、`provider`，尽量填 `usage` 与 `latency_ms`。

---

## 15. 如何添加新 Prompt

1. 在 `factory/prompts/` 新增 `{name}.md`，文件名等于 Agent 的 `prompt_name`。
2. 使用这六个一级标题（缺一不可，测试会查）：

```markdown
# Role
（这段进入 system）

# Objective
...

# Input
- 书名：{{story_title}}
- ...

# Requirements
...

# Constraints
...

# Output Format
只输出 JSON / 或只输出正文。
```

3. 占位符是 `{{variable}}`。未替换的 `{{x}}` 会原样留下。JSON 花括号不会被 `str.format` 吃掉。
4. `# Role` 变成 system，其余标题按顺序拼进 user。
5. 常用变量来自 `StoryContext.prompt_vars()`：`story_title`、`genre`、`style`、`world_context`、`character_context`、`chapter_plan`、`recent_context`、`language`、`chapter_target_words` 等。Agent 可用 `extra_vars` 再补。

`PromptManager` 只做读文件 + 替换，没有模板逻辑。

---

## 16. 测试

全部离线。不要在普通单测里打真实模型。

```bash
pip install -e ".[test]"
pytest
pytest tests/test_demo.py -v    # 只跑离线 demo
```

安装后也可以直接跑：

```bash
factory demo --out /tmp/factory-demo
```

它会强制 `provider=mock`，新建一本 `demo` 书，跑完 setup + 第 1 章，并检查 `outline.json`、`chapters/ch001/final.md`、memory 等产物。逻辑在 `factory/demo.py`，测试在 `tests/test_demo.py`。

核心用例在 `tests/test_core.py`：PromptManager、配置加载、`MockModelProvider`、JSON 解析、memory merge、章节 workflow、改稿上限、storage、Pydantic schema。

可编程 mock：

```python
from factory.models.providers import MockModelProvider
from helpers import install_mock

mock = MockModelProvider(
    by_prompt={"本章任务": {"title": "固定章", "scenes": []}},
    by_purpose={"review": {"score": 10, "must_fix": ["重写"], "passed": False}},
)
install_mock(workflow.models, mock)
```

未命中的 purpose 仍走 `factory/models/mock_data.py` 里的固定 JSON，所以 `factory continue` 在 mock 下可以跑完整章。

---

## 17. Roadmap

已有：mock 全流程、Typer CLI、YAML 配置、分层 memory、JSON/SQLite 存储、用量统计、pytest 离线测试。

近期（仍限制在单机写作管线）：

- 用真实 provider 做一次人工冒烟（不放进默认 CI）
- 补 `pricing` 表，让 `factory stats` 的估费有意义
- 失败章节的 CLI 提示（指出 `pipeline.json` 断点）
- 按书覆盖 `factory.yaml` 的文档与示例

明确不做（除非产品范围改口）：

- RAG / 向量库
- Web UI
- Agent 互调或多智能体自治
- LangGraph 一类编排框架
- 动画、立绘、TTS 管线（见 `docs/`，与本仓库运行时无关）
