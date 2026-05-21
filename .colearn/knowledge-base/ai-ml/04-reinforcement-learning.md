# 强化学习（Reinforcement Learning）

## 核心概念

强化学习是智能体（Agent）通过与环境（Environment）交互学习最优策略的范式。"监督"信号是延迟的奖励（Reward），不是即时标签。

## 马尔可夫决策过程（MDP）

形式化为五元组 (S, A, P, R, γ):
- **S**: 状态空间
- **A**: 动作空间
- **P(s'|s,a)**: 状态转移概率
- **R(s,a)**: 奖励函数
- **γ ∈ [0,1]**: 折扣因子，决定关注长期还是短期回报

## 策略与价值

- **策略 π(a|s)**: 给定状态选动作的规则（确定性或随机）
- **状态价值 V^π(s)**: 从 s 出发执行 π 的期望累积回报
- **动作价值 Q^π(s,a)**: 在 s 选 a 后执行 π 的期望累积回报
- **贝尔曼方程**: V(s) = E[R + γV(s')]，递归分解价值

## 探索 vs 利用（Exploration vs Exploitation）

- **利用（Exploit）**: 选当前最好的动作
- **探索（Explore）**: 试新动作发现潜在更优解
- **ε-greedy**: 以 ε 概率随机，1-ε 概率贪心
- **UCB / Thompson Sampling**: 不确定性导向的探索

## 三大方法族

### 1. 基于价值（Value-Based）

学习 Q 函数，从中导出策略。
- **Q-Learning**: off-policy，学最优 Q*
- **DQN（Deep Q-Network）**: 神经网络拟合 Q，加经验回放 + target network 稳定训练（Atari 2013）

### 2. 基于策略（Policy-Based）

直接参数化策略 π_θ，对期望回报做梯度上升。
- **REINFORCE**: 朴素策略梯度，方差大
- **A2C/A3C**: 加 critic 估计基线，降方差

### 3. Actor-Critic

策略网络（Actor）+ 价值网络（Critic）协同。
- **PPO（Proximal Policy Optimization）**: 限制策略更新幅度，稳定且简单，目前主流
- **SAC（Soft Actor-Critic）**: 最大熵框架，连续控制 SOTA

## 模型相关 vs 模型无关

- **Model-Free**: 不学环境模型，直接学策略/价值（DQN、PPO）
- **Model-Based**: 先学 P 和 R 模型，再规划（AlphaZero、Dreamer）

## 重要应用

- **AlphaGo/AlphaZero**: 蒙特卡洛树搜索 + 深度网络下围棋/象棋
- **机器人控制**: SAC + 仿真训练再 sim-to-real
- **RLHF（用于 LLM）**: 用 PPO 把人类偏好作为奖励信号，对齐大模型行为
- **推荐系统**: 把用户停留/点击作为奖励优化长期参与度

## 挑战

- **样本效率低**: 需要海量交互
- **奖励工程**: 设计稀疏/欺骗性奖励容易导致 reward hacking
- **泛化性差**: 训练环境的策略难迁移到新环境
- **可解释性**: 黑盒决策难以审计
