# 大模型响应速度测试工具

## 📌 项目简介

本子目录旨在对多个主流大语言模型（LLM）在**相同 Prompt 下**的响应性能进行量化测试，主要包括以下三个关键指标：

1. **tokens_per_second**：单位时间内输出 token 的速度（推理吞吐率）
2. **first_token_latency**：从请求发出到返回第一个 token 所花的时间（首响应延迟）
3. **normalized_latency**：归一化延迟，用于横向对比模型在不同 Prompt 长度下的响应效率

这些指标能帮助开发者更准确地评估不同模型在实际应用中的响应速度表现，特别适合对响应时间敏感的应用场景（如对话系统、搜索补全等）。

---

## 📊 指标解释

| 指标名称              | 含义说明 |
|-----------------------|-----------|
| **tokens_per_second** | 模型生成 token 的平均速度，计算方式为 `生成 token 数 ÷ 推理时间（秒）`，数值越大代表生成越快。 |
| **first_token_latency** | 从发送请求到收到第一个 token 的时间（秒），反映了模型的首次响应速度。这个值越小越好，越快给用户反馈。 |
| **normalized_latency** | 将延迟按 prompt 长度进行归一化处理，方便不同长度 prompt 间的对比，一般计算方式为 `first_token_latency ÷ prompt_token_count`。这个值越小，说明模型对长 prompt 更稳定，扩展性更好。 |

---

## ⚙️ 使用说明

### 1. API Key 设置

本项目**不包含任何模型的 API KEY**，请使用者自行配置。推荐将密钥保存到本地环境变量或 `.env` 文件中。

示例 `.env` 文件：

```env
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_claude_key
```

### 2. 代理设置说明

如果你使用代理访问外网（如在中国大陆），请根据实际网络环境**决定是否启用代码中的代理设置**。

proxies = {
    "http": "http://127.0.0.1:7890",
    "https": "http://127.0.0.1:7890"
}
# 可根据需要开启或注释代理代码

---

## ✅ 支持的模型（持续更新中）

- OpenAI GPT-3.5 / GPT-4 / GPT-4 Turbo
- Claude 1 / 2 / 3 系列
- Gemini Pro 系列
- Mistral / Mixtral
- 其他支持 OpenAI/Anthropic 接口风格的模型

---

## 🧪 测试输出格式

测试输出格式如下（JSON示例）：

{
  "model": "gpt-4",
  "prompt_name": "qa_prompt_01",
  "first_token_latency": 1.23,
  "tokens_per_second": 12.56,
  "normalized_latency": 0.034
}

---

## 📮 反馈与建议

欢迎提交 issue 或 PR 来优化本测试工具。如有合作意向，也欢迎联系作者。
