# 53 - AI 动画生成 Agent Skills 拆解方案

> Version：v1.0　Last Update：2026-07
> Status：Active（后置实施方案，需通过 M3.5 后进入主线）
> 依赖：`11-模块命名规范.md`、`31-系统架构.md`、`43-factory.novel流水线规范.md`、`45-合规与内容安全.md`、`51-一致性Playbook.md`、`52-一致性技术预研方案.md`、`61-数据契约与Schema.md`、`62-AgentSkills实现规范.md`

---

# 1. 文档目的

本文把“文字 → 角色 → 镜头 → 动作 → 声音 → 成片”的 AI 动画实操流程，拆解为本项目可落地的 Agent Skills。

核心原则：

- 不把所有能力塞进 `factory.animation`；动画生产必须拆给 `factory.novel`、`factory.visual`、`factory.animation`、`factory.audio`、`factory.publishing` 与 `center.qa`。
- `factory.animation` 只负责镜头运动、视频片段生成、后期增强与渲染合成，不负责故事创作、角色图训练、配音和平台发布。
- 所有视觉、视频、音频产物必须注册进 `center.asset`，并携带 lineage。
- 任何涉及水印、版权、平台标识的流程必须走合规路线；不把“去水印”作为标准能力。

---

# 2. 总体工业流水线

```
factory.novel
  story / screenplay / beat cards
      │
      ▼
factory.visual
  character sheet / reference pack / keyframe image / LoRA plan
      │
      ▼
factory.animation
  shot list / camera / motion prompt / video segment / upscale / render
      │
      ▼
factory.audio
  dialogue script / voice / music / sfx / subtitle timeline
      │
      ▼
factory.publishing
  format / compliance label / platform package / report
```

`center.qa` 横切检查：

```
身份一致性 · 跨模态一致性 · 时序一致性 · 设定一致性 · 合规
```

---

# 3. 手册步骤到项目模块映射

| 手册步骤 | 项目归属 | 说明 |
|----------|----------|------|
| 故事脚本 Story | `factory.novel` | 由 `skill.novel.screenplay` 输出 Beat Cards |
| 人物设计 Character Sheet | `factory.visual` + `center.asset` | 角色外观、服装、标志物、表情、姿态 |
| 文生图 Image | `factory.visual` | 关键帧、角色图、场景图、道具图 |
| 图生视频 Motion | `factory.animation` | 关键帧转视频，镜头运动，动作连续 |
| 配音配乐 Audio | `factory.audio` | TTS、voice clone、BGM、SFX、字幕时间轴 |
| 剪辑合成 Editing | `factory.animation` + `factory.publishing` | 镜头合成由 animation，平台格式由 publishing |
| 视频增强 Upscale | `factory.animation` | 超分、补帧、稳定性修复 |
| 字幕输出 Subtitle | `factory.audio` + `factory.publishing` | 字幕识别/时间轴归 audio，样式/平台封装归 publishing |

---

# 4. 推荐生产模式

## 4.1 快速模式（Market-First / 动态漫）

适合：短视频测试、动态漫、低成本平台验证。

```
screenplay
  → reference image / 即梦 / MJ / 快速出图
  → 闭源图生视频工具（Runway / 可灵 / 即梦 / 海螺等）
  → 剪映 / PR 快速合成
  → 自动字幕
  → 发布测试
```

特点：

- 快速出信号。
- 人物一致性弱于高质量模式。
- 适合作为 `21` Phase 0/1 的视频形式候选。
- 不作为最终 IP 资产基线，除非市场信号强且成本可控。

## 4.2 高质量模式（IP 资产 / 精品动画）

适合：角色 IP、系列动画、长期复用资产。

```
screenplay
  → character sheet
  → canonical reference pack
  → LoRA / reference-based identity
  → SDXL / FLUX / ControlNet keyframes
  → Wan / AnimateDiff / CogVideo 等视频模型
  → voice clone / TTS / music / SFX
  → PR / DaVinci / 自动化合成
  → upscale / interpolation
  → compliance label / subtitle / publishing package
```

特点：

- 一致性更强。
- 成本更高。
- 必须通过 `52` 的 M3.5 验收门后再进入主线。
- 全部本地：轻量任务（spec、prompt、资产管理、评测）与写作白天并行；LoRA、关键帧批量生成、视频生成与重型后处理走本地夜间独占显存批处理（见 `32` §4、`62` §10）。

---

# 5. Agent Skills 拆解

## 5.1 `factory.novel`

| Skill | 输入 | 输出 | 说明 |
|-------|------|------|------|
| `skill.novel.screenplay` | chapter / plot / knowledge snapshot | Beat Cards | 文学意图层，已有规范见 `43` |
| `skill.novel.visual_prompt` | Beat Cards / appearance spec | visual prompt draft | 可选：把 Beat 转为视觉提示词草案，最终由 `factory.visual` 收束 |

## 5.2 `factory.visual`

| Skill | 输入 | 输出 | 说明 |
|-------|------|------|------|
| `skill.visual.character_sheet` | character knowledge / appearance spec | character sheet | 人物卡、服装、表情、姿态 |
| `skill.visual.reference_pack` | character sheet | canonical references | 多角度定妆图、表情图、姿态图 |
| `skill.visual.lora_plan` | reference pack / target style | LoRA training plan | 训练参数、样本清单、本地夜间 GPU 时段需求 |
| `skill.visual.keyframe_image` | shot spec / reference asset | keyframe image | 每镜头关键帧 |
| `skill.visual.controlnet_pose` | shot action / layout | pose/control assets | 姿态、深度、边缘等控制条件 |
| `skill.visual.register` | generated assets | AssetID / version | 写入 `center.asset` |

## 5.3 `factory.animation`

| Skill | 输入 | 输出 | 说明 |
|-------|------|------|------|
| `skill.anim.storyboard` | Beat Cards / AssetID | production storyboard | 生产镜头表，见 `31` / `43` 边界 |
| `skill.anim.shotlist` | storyboard | shot list | 镜头编号、时长、角色、场景、资产 |
| `skill.anim.camera` | shot list | camera plan | 镜头运动、景别、角度、节奏 |
| `skill.anim.motion_prompt` | keyframe / camera plan | motion prompt | 图生视频提示词与负面约束 |
| `skill.anim.video_generate` | keyframe / motion prompt | video segments | 本地 ComfyUI 生成片段（独占 GPU，夜间批处理） |
| `skill.anim.frame_consistency` | video segments / reference | consistency report | 帧间身份漂移、动作变形检查 |
| `skill.anim.interpolate` | video segment | interpolated video | 补帧，提升帧率与平滑度 |
| `skill.anim.upscale` | video segment | upscaled video | 超分、锐化、降噪 |
| `skill.anim.edit_plan` | segments / audio timeline | edit decision list | 镜头顺序、转场、节奏点 |
| `skill.anim.render` | edit decision list / assets | final video draft | 初版成片或可发布前包 |

## 5.4 `factory.audio`

| Skill | 输入 | 输出 | 说明 |
|-------|------|------|------|
| `skill.audio.dialogue_script` | screenplay / chapter | dialogue script | 分角色台词、旁白、情绪标签 |
| `skill.audio.voice_casting` | character voice spec | voice assignment | 角色音色绑定 |
| `skill.audio.tts` | dialogue script / voice assignment | voice clips | 文转语音 |
| `skill.audio.voice_clone` | voice samples / character | voice embedding/model | 声音克隆，长期资产 |
| `skill.audio.music_cue` | beat emotion / scene | BGM cues | 音乐情绪点 |
| `skill.audio.sfx` | shot list / scene | SFX list/clips | 环境音、打斗音效 |
| `skill.audio.subtitle_timeline` | voice clips / ASR | subtitle timeline | 字幕时间轴 |

## 5.5 `factory.publishing`

| Skill | 输入 | 输出 | 说明 |
|-------|------|------|------|
| `skill.publish.label` | final video / platform policy | labeled asset | AIGC 标识、水印、版权声明 |
| `skill.publish.format` | final video / subtitle | platform package | 分辨率、码率、封面、标题 |
| `skill.publish.adapt` | platform package | per-platform package | 平台差异适配 |
| `skill.publish.push` | platform package | publish result | 发布或人工发布包 |
| `skill.publish.report` | platform metrics | report | 回传 `center.operation` |

## 5.6 `center.qa`

| Skill | 输入 | 输出 | 说明 |
|-------|------|------|------|
| `skill.qa.identity_consistency` | image/video / reference | identity score | 角色身份一致性 |
| `skill.qa.cross_modal_consistency` | text spec / image/video/audio | match report | 文图声对齐 |
| `skill.qa.motion_consistency` | video segment | motion report | 帧间漂移、形变、动作断裂 |
| `skill.qa.asset_lineage` | AssetID / lineage | lineage report | 资产来源、版本、可追溯 |
| `skill.qa.compliance` | final package | compliance report | AIGC 标识、版权、平台红线 |

---

# 6. 合规替换：不建立“去水印”能力

原实操手册中“去水印流程”不进入本项目标准流水线。

本项目统一替换为：

| 不采用 | 替代流程 |
|--------|----------|
| 去水印 | 使用无水印授权导出 |
| 去水印 | 重新生成自有资产 |
| 去水印 | 局部重绘仅用于自有资产瑕疵修复 |
| 去水印 | 发布前注入 AIGC 标识与版权声明 |

原因：

- 降低版权和平台违规风险。
- 保证 `center.asset` lineage 可追溯。
- 与 `45-合规与内容安全.md` 的发布前合规流程一致。

---

# 7. SOP 检查清单

每个动画项目进入生产前必须检查：

- [ ] 是否有通过 QA 的故事脚本 / Beat Cards。
- [ ] 是否有 Character Sheet。
- [ ] 是否有 canonical reference pack。
- [ ] 是否有人物一致性方案（LoRA / reference-based / de-scope）。
- [ ] 是否有每镜头 Shot List。
- [ ] 是否有每镜头关键帧 Prompt。
- [ ] 是否有视频生成方式（闭源快速 / 开源高质量 / 混合）。
- [ ] 是否有音频情绪标签、角色音色和字幕时间轴。
- [ ] 是否有剪辑节奏和镜头合成计划。
- [ ] 是否完成超分 / 补帧 / 稳定性增强的必要性判断。
- [ ] 是否通过 `center.qa` 的身份、跨模态、时序、设定与合规检查。
- [ ] 是否写入 `center.asset` 并携带 lineage。

---

# 8. 分阶段接入建议

## 8.1 当前阶段（只做 `factory.novel`）

仅保留接口意识：

- `skill.novel.screenplay` 输出 Beat Cards 时，应包含后续视觉/动画需要的字段。
- `novel_factory` 不实现视觉、动画、音频 skills。
- 任何动画相关任务不进入当前 Sprint。

## 8.2 下一阶段（动态漫 / 有声书验证）

优先接入：

- `factory.audio`：TTS、字幕时间轴、简单 BGM/SFX。
- `factory.visual`：Character Sheet、封面、关键静帧。

暂不接入：

- LoRA 训练。
- 开源视频模型。
- 全自动剪辑。

## 8.3 M3.5 后（动画工厂）

进入：

- `skill.anim.storyboard`
- `skill.anim.shotlist`
- `skill.anim.keyframe_plan`
- `skill.anim.video_generate`
- `skill.anim.frame_consistency`
- `skill.anim.upscale`
- `skill.anim.render`

条件：

- `52` 四维一致性基线通过。
- 本地单卡 GPU 时段预算可支撑目标产能（每周 2 集，见 `32` §4）。
- 至少有一个市场验证形式跑通。

---

# 9. 一句话总结

AI 动画工厂不是单一视频生成器，而是由 `screenplay + character sheet + reference assets + shot list + motion model + audio timeline + QA` 组成的可复用生产线。本项目吸收动画实操手册的最佳方式，是把它拆成多模块 Agent Skills，并把一致性与合规作为进入动画主线的前置门。
