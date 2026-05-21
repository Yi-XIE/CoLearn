# Transformer 与大语言模型（Transformer & LLM）

## Transformer 起源

2017 年 Google 论文《Attention is All You Need》提出 Transformer，抛弃 RNN 的循环结构，纯注意力机制。

## 自注意力机制（Self-Attention）

核心公式:

```
Attention(Q, K, V) = softmax(QK^T / √d_k) · V
```

- Q（Query）: 当前 token 想问什么
- K（Key）: 每个 token 提供的"索引"
- V（Value）: 每个 token 携带的内容
- 缩放因子 √d_k: 防止 softmax 梯度饱和

## 多头注意力（Multi-Head Attention）

并行多组 (Q,K,V) 投影，每"头"学习不同的关系（语法、语义、共指等），最后拼接。

## Transformer 架构

- **Encoder**: 自注意力 + FFN，处理输入序列
- **Decoder**: 带 mask 的自注意力 + cross-attention + FFN，生成输出
- **位置编码**: 注意力本身无序，需要正弦/绝对/旋转位置编码（RoPE）

## 模型家族

| 类型 | 代表 | 特点 |
|------|------|------|
| Encoder-only | BERT | 双向理解，分类/抽取 |
| Decoder-only | GPT 系列、Claude、LLaMA | 自回归生成 |
| Encoder-Decoder | T5、BART | 翻译、摘要 |

## 大语言模型（LLM）特征

### Scaling Laws

模型性能随参数规模、数据规模、计算量幂律提升（Kaplan et al. 2020）。

### 涌现能力（Emergent Abilities）

某些能力在模型规模超过临界点后突然出现，如 few-shot 学习、思维链推理。

### 预训练 + 微调

1. **预训练（Pretraining）**: 海量无标注文本上做语言建模
2. **指令微调（SFT）**: 标注的"指令-回答"对
3. **RLHF**: 人类反馈的强化学习，让输出符合偏好
4. **DPO/Constitutional AI**: 简化的偏好对齐方法

### 关键技术

- **In-Context Learning**: 不更新参数，靠 prompt 中的示例学习
- **Chain-of-Thought (CoT)**: 让模型先推理再答，提升复杂任务表现
- **Tool Use**: 模型调用搜索/计算器/代码执行扩展能力
- **RAG（Retrieval-Augmented Generation）**: 外部知识库检索 + 生成，缓解幻觉

## 局限性

- **幻觉（Hallucination）**: 自信地编造错误事实
- **上下文窗口**: 过长输入会丢信息（即使是 100K+ 窗口）
- **推理 vs 记忆**: 数学/逻辑短板，本质是模式匹配
- **训练数据截止**: 不知道训练后发生的事
