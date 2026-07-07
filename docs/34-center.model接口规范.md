# 34 - center.model 接口规范

> Version：v1.1（新增 ComfyUI 图像/视频、本地 TTS 一等后端 + GPU 队列感知）　Last Update：2026-07
> Status：Active
> 依赖：`31-系统架构.md`、`32-硬件与部署方案.md`、`33-模型选型策略.md`

---

# 1. 文档目的

定义 `center.model` 对所有 skill 暴露的**统一接口**，屏蔽底层后端差异（本地 Ollama/vLLM · 本地 ComfyUI 图/视频 · 本地 TTS · 可选云 API）。所有 skill 只调用本文档描述的接口，不得直接调用底层后端。

> **v1.1 变化**：本地 RTX 5090 CUDA 工作站下，图像/视频（ComfyUI）与 TTS 为一等本地后端。所有占 GPU 的后端调用须经 **GPU 队列调度器**申请显存额度（见 `32` §7、`62` §10），不得绕过直连 GPU。

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

# 图像生成（ComfyUI，占 GPU，经队列调度）
image = client.generate_image(prompt=..., lora_ids=[...], seed=...)

# 视频生成（ComfyUI，独占 GPU，夜间批处理）
video = client.generate_video(keyframes=[...], motion_prompt=..., duration_sec=5)

# TTS（本地，多说话人，绑定 Character voice_id）
audio = client.tts(text=..., voice_id="knowledge.character.0001")
```

## 2.2 ModelClient 内部路由

```
ModelClient(profile)
   │
   ├─ profile → config → backend 选择
   │    novel_write   → Ollama/vLLM（本地 14~32B 量化，白天常驻）
   │    novel_review  → Ollama 轻量模型（本地）
   │    embed         → bge-m3 / gte 中文（本地，1024 维）
   │    image_gen     → ComfyUI（本地，占 GPU → 申请队列）
   │    video_gen     → ComfyUI（本地，独占 GPU → 申请队列，夜间批处理）
   │    tts           → 本地 TTS（XTTS/CosyVoice/Piper）
   │
   ├─ 占 GPU 的 backend → 先向 GPU 队列调度器申请显存额度（见 62 §10）
   │
   └─ 统一返回 str / Iterator[str] / list[float] / AssetID
```

---

# 3. Profile 配置表（`configs/model_profiles.yaml`）

```yaml
profiles:
  novel_write:
    backend: ollama           # ollama | vllm | comfyui | tts_local | openai_compat
    base_url: http://localhost:11434
    model: qwen2.5:32b-instruct-q4_K_M   # 单卡 32GB 主力；按 33 实测结论填
    timeout_s: 120
    context_window: 32768
    temperature: 0.85
    top_p: 0.95
    gpu_class: llm_resident   # 白天常驻，见 62 §10 显存预算表

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

  image_gen:
    backend: comfyui
    base_url: http://localhost:8188
    workflow: sdxl_character.json  # ComfyUI 工作流
    timeout_s: 120
    gpu_class: image              # 8~16GB，白天按需短时占用

  video_gen:
    backend: comfyui
    base_url: http://localhost:8188
    workflow: wan_i2v.json
    timeout_s: 1800
    gpu_class: video_exclusive    # 24~32GB，独占显存，夜间批处理

  tts:
    backend: tts_local
    engine: xtts                  # xtts | cosyvoice | piper
    timeout_s: 60
    gpu_class: tts                # 2~6GB，与视频错峰

  cloud_fallback:               # 本地后端不可用/队列积压超阈值时的可选溢出
    backend: openai_compat
    base_url: ${CLOUD_API_BASE}
    model: ${CLOUD_MODEL}
    timeout_s: 180
```

> `gpu_class` 字段对接 GPU 队列调度器的显存预算表（`62` §10）：`llm_resident` / `image` / `video_exclusive`（独占锁）/ `tts`。

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
  "model": "qwen2.5:32b-instruct-q4_K_M",
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
ollama pull qwen2.5:32b-instruct-q4_K_M

# 验证 ComfyUI 服务（图像/视频后端）
curl http://localhost:8188/system_stats

# 验证 GPU 可用与显存
nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv

# center.model 健康检查（启动时自动跑，含 GPU 队列调度器就绪检查）
python -m center.model check
```

> 启动检查失败时：LLM 后端不可用 → 降级 `cloud_fallback` 并告警；ComfyUI/GPU 不可用 → 视觉/视频任务置队列暂停（不阻塞写作），告警人工介入（见 `32` §9 监控）。
