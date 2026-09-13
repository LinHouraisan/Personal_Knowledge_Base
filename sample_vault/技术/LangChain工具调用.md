---
created: 2026-09-06
updated: 2026-09-12
tags: [Agent, LangChain, ToolCalling]
status: active
---
# LangChain工具调用

Agent 只获得三个工具：检索笔记、读取指定笔记、查找关联笔记。工具参数不能传入绝对路径，读取范围由 Vault 根目录限制。

每次请求单独收集工具证据，避免并发问答共享来源。若 Agent 没有调用工具，系统会丢弃模型给出的知识结论并返回无法确认。设计依据见 [[模型幻觉约束]]。

