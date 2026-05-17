# CoLearn-v0.2 收口状态

这份文档只记录当前已经落地的主线状态。

## 当前主线

- `webui + runtime_v2 + slim config` 是 CoLearn 的默认主线。
- `LearningState` 已接入回合前注入和回合后写回。
- `LightRAG` 和 `memory` 作为默认工具接入。
- 知识花园、记忆、技能、设置已消费真实数据。

## 已完成

- `runtime_v2` 承担 slim config、prompt 组装、tool 注册、result bridge、learning closure。
- WebUI 主导航已切到真实数据页。
- 默认启动入口已对齐到 `scripts/start-colearn-v2-gateway.ps1`。

## 当前边界

- 主线不再回头改 nanobot 核心 loop。
- 新学习能力只进 `runtime_v2`。
- 默认文档只描述当前主线，不再写旧线推进计划。

## 验收口径

- 启动 gateway 后可进入 WebUI。
- 知识花园、记忆、技能、设置页能展示真实数据。
- `LearningState` 可参与 turn writeback。
- `LightRAG` 配置存在时可执行真实检索。
