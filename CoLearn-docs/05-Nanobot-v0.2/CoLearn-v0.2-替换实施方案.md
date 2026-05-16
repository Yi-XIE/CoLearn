# CoLearn-v0.2 替换实施方案

这份文档承接前面的判断稿：

- [nanobot-v0.2-core-rebase-plan.md](D:/Colearn-nightly/CoLearn-docs/05-Nanobot-v0.2/nanobot-v0.2-core-rebase-plan.md)
- [nanobot-v0.2-code-report-for-CoLearn.md](D:/Colearn-nightly/CoLearn-docs/05-Nanobot-v0.2/nanobot-v0.2-code-report-for-CoLearn.md)
- [CoLearn-LearningState-协议.md](D:/Colearn-nightly/CoLearn-docs/02-Architecture/CoLearn-LearningState-%E5%8D%8F%E8%AE%AE.md)

它回答的是另一个更落地的问题：

**如果我们决定让 CoLearn 直接换到 nanobot v0.2.0 核心上，这件事到底要怎么做。**

当前实施原则是：

- 先换运行底座，再接学习产品层
- 先跑通主链，再逐步收编旧代码
- 先保住 CoLearn 的学习语义，再扩更多 agent 能力

---

## 1. 实施目标

CoLearn-v0.2 的第一阶段目标，不是一次性做成最终产品，而是先完成这件事：

**让 CoLearn 的主运行链，站到 nanobot v0.2.0 的 runtime、WebUI 和 packaging 骨架上。**

更具体一点，就是：

1. 前端主界面切到 nanobot `webui/`
2. 会话驱动和消息流切到 nanobot loop / stream 模型
3. 持续目标切到 `goal_state`
4. provider 兜底切到 `fallback_models`
5. CoLearn 的学习项目、知识库、LearningState 以产品层方式接上去

---

## 2. 目录策略

这一轮不建议直接把所有旧目录推倒重来。更稳的做法是让目录先形成“双层结构”。

### 2.1 上游核心层

保留当前上游代码落点：

- `third_party/nanobot-0.2.0/nanobot-0.2.0`

这份目录先作为：

- 参考实现
- 模块迁移来源
- 未来抽取 core 的母本

短期内不直接在这个目录里做大量定制，避免把上游和 CoLearn 改动搅在一起。

### 2.2 CoLearn 运行层

继续以当前仓库为主工程，但逐步引入一层新的运行封装，建议落在：

- `colearn/runtime_v2/`

这个目录用于承接：

- 基于 nanobot loop 的运行时装配
- CoLearn 专属工具注册
- LearningState 注入
- session / project / goal 的映射规则
- CoLearn 版本的 gateway 接口编排

也就是说：

- 上游 `nanobot` 负责提供结构和实现参考
- `colearn/runtime_v2` 负责把它变成 CoLearn 的运行主干

### 2.3 前端目录策略

现有目录：

- `web/`

建议新建：

- `webui/`

这里的 `webui/` 不是重新发明，而是基于上游 `nanobot/webui` 拷贝一份 CoLearn 工作副本。

原因：

- 需要改品牌、信息架构、功能入口
- 需要和 CoLearn 的 API 适配
- 需要保留以后独立演进空间

短期策略：

- `web/` 保留，用于过渡和对照
- `webui/` 作为新主界面

中期策略：

- 新主链完全迁到 `webui/`
- `web/` 停止继续扩写

---

## 3. 保留、接管、归档

### 3.1 直接接管的上游能力

建议优先吸收这些模块的设计和实现：

- `nanobot/agent/*`
- `nanobot/session/*`
- `nanobot/providers/*`
- `nanobot/config/*`
- `nanobot/web/*`
- `webui/*`
- `hatch_build.py`

这几块共同构成：

- loop
- stream
- session
- provider fallback
- WebUI
- wheel 打包

这就是 CoLearn-v0.2 的新底盘。

### 3.2 CoLearn 必须保留的产品层

这些模块不要丢：

- `colearn/learning/*`
- `colearn/app/*`
- `colearn/knowledge/*`
- `colearn/projects/*`
- `colearn/sessions/*`
- `colearn/sources/*`
- `colearn/retrieval/*`

其中优先级最高的是：

- `LearningState`
- 学习循环编排
- 知识源与资料组织
- 项目级目标语义

这些东西不是上游通用 agent 会替我们解决的。

### 3.3 应该逐步归档的现有部分

以下内容不建议继续作为长期主线扩写：

- `web/` 中围绕现有壳子继续做大量新页面
- `colearn/api/app.py` 里继续堆叠运行时逻辑
- 当前零散的自定义流协议，如果它们和新 WebUI 的流模型冲突

它们可以暂时保留，但要逐步退到：

- 兼容层
- 过渡层
- 旧接口适配层

---

## 4. 新架构分层

替换之后，建议把 CoLearn-v0.2 明确拆成四层。

### 4.1 Core Layer

负责：

- Agent loop
- Session state
- Goal state
- Provider dispatch
- Tool plugin loading
- Stream event model

建议来源：

- nanobot v0.2.0 主 core

### 4.2 Product Runtime Layer

负责：

- Project -> session -> goal 的映射
- LearningState 注入 runtime context
- 知识库 / source library 的工具挂载
- CoLearn 的 settings / auth / bootstrap 组装

建议落点：

- `colearn/runtime_v2/*`

### 4.3 Product Domain Layer

负责：

- 学习项目
- 资料库
- 检索
- 学习循环
- 产出物

建议沿用：

- `colearn/learning/*`
- `colearn/knowledge/*`
- `colearn/projects/*`
- `colearn/retrieval/*`

### 4.4 Experience Layer

负责：

- WebUI
- 会话视图
- 项目侧栏
- 学习目标展示
- 设置面板
- 未来的知识库、学习图谱、学具入口

建议落点：

- `webui/`

---

## 5. 第一阶段最小主链

不要上来就把所有能力一起搬。先锁一条最小闭环。

### 5.1 第一阶段必须跑通的能力

1. 登录 / bootstrap
2. 会话列表
3. 单线程聊天
4. 流式响应
5. `/goal` 持续目标
6. Goal 状态前端展示
7. 一个最小 CoLearn 学习工具
8. 一个最小 knowledge 检索入口

只要这 8 项打通，我们就已经不是“研究 nanobot”，而是已经站到了新底座上。

### 5.2 第一阶段可以先不做的能力

- 完整知识库管理界面
- 多 provider 全量支持
- 图像生成产品功能
- 多渠道桥接
- 配对 / 私信审批
- 复杂项目管理页

---

## 6. 具体实施阶段

## 阶段 A：建立新工作分支和新入口

目标：

- 建立独立施工线
- 不污染现有可运行主链

建议：

1. 新建分支，例如 `rebase/nanobot-v0.2-core`
2. 新建 `colearn/runtime_v2/`
3. 新建 `webui/`
4. 补一份 `README`，明确新主链启动方式

交付物：

- 新目录在仓库里就位
- 文档说明清楚“旧链”和“新链”并行

## 阶段 B：跑通 WebUI 和 gateway 壳

目标：

- 先把上游 WebUI 在 CoLearn 仓库里跑起来
- 让它能打到 CoLearn 的新后端入口

实施重点：

1. 拷贝上游 `webui/` 到仓库主目录工作副本
2. 保留 Vite dev proxy 结构
3. 新增 CoLearn 版本的：
   - `/webui/bootstrap`
   - `/api/sessions`
   - `/api/sessions/{key}/webui-thread`
4. 让前端能看到：
   - session list
   - chat view
   - settings shell

交付物：

- `webui/` 本地可启动
- 能打开 CoLearn 版本的聊天界面

## 阶段 C：接入 loop、stream 和 goal_state

目标：

- 把 runtime 主循环从“自定义散装编排”切到更统一的 core

实施重点：

1. 参考上游 `AgentLoop.from_config()` 建 CoLearn 版本装配器
2. 用新 loop 跑通一次用户消息 -> 工具 -> 回复
3. 接入 `goal_state`
4. 让前端能看到 `goal_status` / `goal_state`
5. 对齐 wall timeout 与长任务状态

交付物：

- 有真实可用的持续目标推进链
- Goal 在压缩和长回合后仍然保持

## 阶段 D：把 LearningState 压到新 core 上

目标：

- 让 CoLearn 的核心差异真正进入 runtime

实施重点：

1. 把 `BoardFacts` 注入每轮 runtime context
2. 把 `TurnPolicy` 接成回合策略输入
3. 把 `LearningEvent` 接成回合结束后的持久化更新
4. 建立 project / session / goal / board 的映射规则

交付物：

- CoLearn 不只是换了前端，而是学习系统真的跑在新底座上

## 阶段 E：知识库和学习工具接入

目标：

- 让 CoLearn 的 source / retrieval / study 工具能在新 runtime 里发力

实施重点：

1. 把 knowledge 检索能力封装成工具
2. 把资料库与 session 关系挂起来
3. 把至少一个学习工具接入插件层
4. 定义图像生成接口位，但不做完整产品能力

交付物：

- 新 runtime 能调用 CoLearn 学习工具
- 新 WebUI 能消费对应结果

## 阶段 F：旧链退役

目标：

- 把旧链从主线路里挪开

实施重点：

1. 停止继续扩写旧 `web/`
2. 把旧接口改为兼容层或迁移层
3. README 改为新主链启动方式
4. 打通 wheel / 本地安装 / 一键启动路径

交付物：

- CoLearn-v0.2 拥有明确单一路径

---

## 7. 模块映射建议

### 7.1 Runtime 装配

建议新增：

- `colearn/runtime_v2/bootstrap.py`
- `colearn/runtime_v2/loop_adapter.py`
- `colearn/runtime_v2/context_builder.py`
- `colearn/runtime_v2/tool_registry.py`
- `colearn/runtime_v2/goal_bridge.py`

### 7.2 WebUI 适配

建议新增：

- `colearn/api/webui_bootstrap.py`
- `colearn/api/webui_sessions.py`
- `colearn/api/webui_stream.py`
- `colearn/api/webui_settings.py`

### 7.3 LearningState 桥接

建议新增：

- `colearn/learning/runtime_projection.py`
- `colearn/learning/goal_mapping.py`
- `colearn/learning/event_sink.py`

### 7.4 知识库工具桥接

建议新增：

- `colearn/knowledge/tooling.py`
- `colearn/retrieval/tooling.py`

---

## 8. 风险与控制

### 8.1 风险：换底座期间双线并行太久

问题：

- 旧 `web/` 和新 `webui/` 同时存在，容易让团队继续往旧链上加东西

控制：

- 明确规定新功能只进 `webui/`
- 旧 `web/` 只修阻塞性问题

### 8.2 风险：上游结构吸收过快，学习产品层反而被淹没

问题：

- 很容易把时间都花在“对齐 nanobot 功能面”上

控制：

- 每一阶段都问一句：这件事是否直接服务 CoLearn 的学习主链

### 8.3 风险：协议层分叉太多

问题：

- 如果同时维护旧 `api/v1/*` 和新 WebUI 协议，后面容易两头都难受

控制：

- 新主链优先围绕 WebUI 需要的协议建
- 旧 `api/v1/*` 只做兼容，不继续当真主线扩展

---

## 9. 首批执行清单

这一轮真正开工时，建议先做下面这些最值当的事：

1. 建 `rebase/nanobot-v0.2-core` 分支
2. 建 `webui/` 工作副本
3. 建 `colearn/runtime_v2/`
4. 跑通 `/webui/bootstrap`
5. 跑通 session list
6. 跑通一条最小聊天流
7. 接 `/goal`
8. 接 LearningState runtime 注入

做到这里，CoLearn-v0.2 就已经立起来了。

---

## 10. 最终判断

这次替换不应该被理解成“推翻重来”。

更准确地说，这是：

**把 CoLearn 从一套还在自己补基建的原型，切换到一套已经具备成熟 agent 底盘的产品骨架上。**

换完之后，我们真正该花力气的地方会更清楚：

- 学习目标如何持续推进
- 学习状态如何建模
- 知识与资料如何转化成学习上下文
- 工具如何真正服务教学与学习

这几件事，才是 CoLearn 自己最有价值的部分。
