# nanobot v0.2 核心接管状态

这份文档只保留当前结论。

## 结论

- `nanobot v0.2` 作为运行底座成立。
- CoLearn 的主线已经落到 `webui + runtime_v2 + slim config`。
- 旧前端树已删除。

## 当前主线

- `runtime_v2` 负责学习回合封装。
- `LightRAG` 和 `memory` 负责学习检索。
- `LearningState` 负责写回。

## 后续

- 只继续补主线能力，不再写旧线推进计划。
