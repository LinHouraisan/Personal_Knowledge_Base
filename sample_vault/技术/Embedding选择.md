---
created: 2026-09-05
updated: 2026-09-09
tags: [RAG, Embedding, 本地模型]
status: active
---
# Embedding选择

演示环境默认通过 Ollama 使用 bge-m3。原因是中文检索能力、部署成本和隐私之间比较均衡，而且可以通过 OpenAI-compatible 接口与应用解耦。

单元测试不调用真实模型，而是注入确定性的 Fake Embedder。这可以验证 [[RAG检索流程]]，但不能替代真实语料上的召回率评测。

