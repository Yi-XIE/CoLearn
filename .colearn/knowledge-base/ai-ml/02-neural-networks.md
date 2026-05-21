# 神经网络与深度学习（Neural Networks & Deep Learning）

## 神经元基础

人工神经元接收输入 x = (x1, ..., xn)，加权求和后过激活函数:

```
y = σ(w·x + b)
```

其中 w 是权重向量，b 是偏置，σ 是激活函数。

## 常见激活函数

- **Sigmoid**: σ(z) = 1/(1+e^-z)，输出 (0,1)，但梯度饱和
- **Tanh**: 输出 (-1,1)，零中心化
- **ReLU**: max(0, z)，简单高效，深度网络默认选择
- **Leaky ReLU / GELU / Swish**: ReLU 改进，缓解 dead neuron

## 网络架构

### 前馈网络（MLP）

层叠 Linear + Activation。每层输出作为下层输入。万能逼近定理：足够宽的两层网络可以逼近任意连续函数。

### 卷积神经网络（CNN）

针对图像。核心: 卷积层（局部感知 + 权重共享）+ 池化层（降采样）。
- LeNet (1998): 手写数字
- AlexNet (2012): ImageNet 突破
- ResNet (2015): 残差连接，训练超深网络

### 循环神经网络（RNN/LSTM/GRU）

处理序列。RNN 朴素版本梯度消失，LSTM/GRU 通过门控机制保留长程依赖。Transformer 之前的序列建模主力。

## 训练机制

1. **前向传播**: 计算预测值
2. **损失计算**: L = loss(y_pred, y_true)
3. **反向传播（Backprop）**: 链式法则计算 ∂L/∂w
4. **参数更新**: w ← w - η·∂L/∂w（η 是学习率）

## 优化器

- **SGD**: 朴素梯度下降，加 momentum 加速
- **Adam**: 自适应学习率，目前默认选择
- **AdamW**: 修正 Adam 的 weight decay

## 关键技巧

- **Batch Normalization**: 稳定训练，缓解内部协变量偏移
- **Dropout**: 训练时随机丢弃神经元，防止过拟合
- **Learning Rate Schedule**: warmup + cosine decay
- **梯度裁剪**: 防止梯度爆炸

## 深度学习突破点

深度学习≠"很深的神经网络"。关键在于:
1. 端到端学习: 不需要手工特征工程
2. 表示学习: 浅层学边缘/纹理，深层学概念
3. 数据规模: 千万级以上样本时优势显著
