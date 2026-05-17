# CoLearn 顶层组装路径

这份文档只记录当前主线。

## 当前主线

- `webui + runtime_v2 + slim config` 是默认主线。
- `runtime_v2` 负责 prompt、tool、result bridge、learning closure。
- `LightRAG` 和 `memory` 是默认学习工具。
- `LearningState` 已进入回写链路。

## 已完成

- WebUI 主导航已接入真实数据。
- 旧 `web/` 前端树已删除。
- 旧 `colearn/runtime/*` 主逻辑已删除。

## 当前边界

- 主线继续围绕 `colearn/app/learning_orchestrator.py`、`colearn/runtime_v2/*`、`webui/src/*` 展开。
- 文档不再保留旧线推进计划。
