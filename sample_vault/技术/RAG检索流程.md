---
created: 2026-09-05
updated: 2026-09-11
tags: [RAG, 检索, 技术]
status: active
---
# RAG检索流程

索引流程为 Markdown 扫描、Frontmatter 解析、段落分块、Embedding 和向量持久化。查询时先计算问题向量，再使用余弦相似度选择相关 Chunk。

Chunk 必须携带标题、相对路径、标签和所属标题。回答时这些字段会变成结构化来源，并生成可点击的 Obsidian 地址。模型选择记录在 [[Embedding选择]]，可信度约束见 [[模型幻觉约束]]。

