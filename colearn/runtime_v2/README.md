# CoLearn runtime_v2

`runtime_v2` 是 CoLearn 基于 `nanobot v0.2.0` 的新主运行线落点。

当前阶段它先承担三件事：

1. 固定 CoLearn-v0.2 的瘦身启动配置
2. 固定第一批保留能力与禁用范围
3. 给后续 `LightRAG` 接入和学习状态轻注入提供稳定入口

当前相关文件：

- [profile.py](D:/Colearn-nightly/colearn/runtime_v2/profile.py)
- [executor.py](D:/Colearn-nightly/colearn/runtime_v2/executor.py)
- [learning_closure.py](D:/Colearn-nightly/colearn/runtime_v2/learning_closure.py)
- [prompting.py](D:/Colearn-nightly/colearn/runtime_v2/prompting.py)
- [result_bridge.py](D:/Colearn-nightly/colearn/runtime_v2/result_bridge.py)
- [tooling.py](D:/Colearn-nightly/colearn/runtime_v2/tooling.py)
- [nanobot-v0.2-slim.config.json](D:/Colearn-nightly/.colearn/nanobot-v0.2-slim.config.json)

当前策略：

- `nanobot` 负责 runtime / loop / WebUI / session / goal / stream
- CoLearn 负责 learning / retrieval / project / source library

启动新主线：

1. 设置环境变量：
   - `OPENAI_API_KEY`
   - `OPENAI_API_BASE`
   - `COLEARN_NANOBOT_TOKEN_ISSUE_SECRET`
2. 运行脚本：
   - [start-colearn-v2-gateway.ps1](D:/Colearn-nightly/scripts/start-colearn-v2-gateway.ps1)
3. 打开：
   - `http://127.0.0.1:8765`

下一步代码接入重点：

1. 让 `NanobotTurnExecutor` 读取 `runtime_v2` 的配置与默认工具选择
2. 让执行器本体落在 `runtime_v2/executor.py`
3. 让 learning closure 通过 `runtime_v2/learning_closure.py` 统一接入
4. 让 prompt 组装通过 `runtime_v2/prompting.py` 统一接入
5. 让结果归一化通过 `runtime_v2/result_bridge.py` 统一接入
6. 让 `memory + lightrag` 的注册通过 `runtime_v2/tooling.py` 统一接入
7. 在新主链上验证一次真实知识检索对话
