# Colearn-nightly

这是一个从 `nanobot core` 出发的独立 CoLearn 组装工作区。

当前位置：

1. 已复制裁剪后的 `third_party/nanobot-core`
2. 已复制相关架构文档到 `CoLearn-docs/`
3. 已完成组装路径第一步的最小骨架：
   - `colearn/learning`
   - `colearn/runtime`
   - `colearn/projects`
   - `colearn/sessions`
   - `colearn/knowledge`
   - `colearn/memory`
4. 已从 `D:\CoLearn-release\web` 裁剪并复制一份 CoLearn 前端壳到 `web/`
   - 保留 `chat / knowledge / memory / settings`
   - 保留 `sidebar / session 管理 / chat composer / message list / preview drawer`
   - 不带 `admin / agents / playground / co-writer / book` 等无关产品面

当前目标：

1. 先固定 CoLearn 主协议
2. 再把 LightRAG 收成独立 retrieval 层
3. 再把 nanobot core 接成真实底层执行器

文档入口：

1. `CoLearn-docs/02-Architecture/CoLearn-顶层组装路径.md`
2. `CoLearn-docs/02-Architecture/CoLearn-学习循环实施手册.md`

说明：

这套目录不再以旧 `CoLearn-release` 作为宿主壳，而是从独立工作区开始组装。
