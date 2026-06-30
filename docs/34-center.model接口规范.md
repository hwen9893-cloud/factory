# 34 - center.model 接口规范

> Version：v1.0　Last Update：2026-06
> Status：Active
> 依赖：`31-系统架构.md`、`32-硬件与部署方案.md`、`33-模型选型策略.md`

---

# 1. 文档目的

定义 `center.model` 对所有 skill 暴露的**统一接口**，屏蔽底层后端差异（Ollama 本地 / MLX 本地 / 云 API）。所有 skill 只调用本文档描述的接口，不得直接调用底层后端。

---

# 2. 统一接口设计

## 2.1 Python 接口（所有 skill 调用此层）

```python
from center.model import ModelClient

client = ModelClient(profile="novel_write")   # 按 skill 类型选 profile

# 同步调用（短 prompt / 审校）
response: str = client.complete(
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ],
    max_tokens=4096,
)

# 流式调用（长文写作，实时反馈进度）
for chunk in client.stream(messages=[...], max_tokens=6000):
    print(chunk, end="", flush=True)

# Embedding（检索 / QA 相似度）
vector: list[float] = client.embed(text="角色设定文本")  # len=1024 (bge-m3)
```

## 2.2 ModelClient 内部路由

```
ModelClient(profile)
   │
   ├─ profile → config → backend 选择
   │    novel_write   → Ollama / MLX（本地 70B 量化）
   │    novel_review  → Ollama 轻量模型（本地 14B）
   │    embed         → Ollama nomic-embed / bge 中文
   │    tts           → 专用 TTS 后端（见 factory.audio）
   │
   └─ 统一返回 str / Iterator[str] / list[float]
```

---

# 3. Profile 配置表（`configs/model_profiles.yaml`）

```yaml
profiles:
  novel_write:
    backend: ollama           # ollama | mlx | openai_compat
    base_url: http://localhost:11434
    model: qwen2.5:72b-instruct-q4_K_M   # 按 33 实测结论填
    timeout_s: 120
    context_window: 32768
    temperature: 0.85
    top_p: 0.95

  novel_review:
    backend: ollama
    model: qwen2.5:14b-instruct-q4_K_M
    timeout_s: 60
    context_window: 8192
    temperature: 0.2             # 审校要求更确定性

  embed:
    backend: ollama
    model: bge-m3                # 1024 维，中文优先；英文备选 nomic-embed-text（768 维）
    timeout_s: 30

  cloud_fallback:               # Ollama 挂了时的备用
    backend: openai_compat
    base_url: ${CLOUD_API_BASE}
    model: ${CLOUD_MODEL}
    timeout_s: 180
```

---

# 4. 重试 / 超时 / Fallback 策略

| 情况 | 行为 |
|------|------|
| 超时（首次） | 自动重试 1 次，timeout × 1.5 |
| 超时（二次） | 切换 `cloud_fallback` profile |
| 云也超时 | 抛出 `ModelUnavailableError`，任务状态置 `failed`，人工介入 |
| 上下文超长 | 自动截断旧对话（保留 system + 最近 N 轮），记录截断日志 |
| 模型输出空串 | 视为软错误，重试最多 3 次 |

---

# 5. 上下文窗口管理（长文写作关键）

```python
class ContextBuilder:
    """
    为 skill.novel.chapter 等长文 skill 构建 messages。
    优先级（高 → 低）：
      1. system prompt（固定，约 800 tokens）
      2. 当前章节相关设定（从 center.knowledge 查，约 1200 tokens）
      3. 上一章结尾段落（约 400 tokens，维持叙事连续）
      4. 本章大纲 / 场景卡（约 600 tokens）
      5. 用户任务指令（约 200 tokens）
    总预算：≤ context_window × 0.6（留 40% 给生成）
    """
    def build(self, knowledge_refs, prev_chapter_tail, scene_card, task) -> list[dict]:
        ...
```

> 超出预算时按优先级从低到高截断，**system prompt 和当前设定永不截断**。

---

# 6. 日志规范

每次 `ModelClient` 调用自动写结构化日志（对接 `72` 评测）：

```json
{
  "ts": "2026-06-30T09:00:00Z",
  "skill": "skill.novel.chapter",
  "profile": "novel_write",
  "backend": "ollama",
  "model": "qwen2.5:72b-instruct-q4_K_M",
  "input_tokens": 2340,
  "output_tokens": 1850,
  "latency_ms": 42000,
  "fallback": false,
  "truncated": false
}
```

---

# 7. 本地环境启动检查

```bash
# 验证 Ollama 服务
curl http://localhost:11434/api/tags | jq '.models[].name'

# 验证目标模型已拉取
ollama pull qwen2.5:72b-instruct-q4_K_M

# center.model 健康检查（启动时自动跑）
python -m center.model check
```

> 启动检查失败时降级到 `cloud_fallback`，并发出告警（见 `32` §8 监控）。
