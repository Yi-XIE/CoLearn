# CoLearn-v0.2 接管状态

这份文档记录 CoLearn 当前的接管结果。

## 已完成

- `colearn/runtime_v2` 已成为主运行封装层。
- `LearningState` 已进入稳定回写链路。
- `LightRAG` 已接入检索链路。
- WebUI 已切换到真实数据产品面。

## 当前主线

- 启动入口：`scripts/start-colearn-v2-gateway.ps1`
- 默认配置：`.colearn/nanobot-v0.2-slim.config.json`
- 默认运行层：`colearn/runtime_v2`

## 验收口径

- 主导航四页可用。
- `runtime_v2` 负责 prompt、tool、result、closure。
- `LightRAG` 配置可驱动真实检索。
- `LearningState` 可参与回写。
