---
created: 2026-09-09
updated: 2026-09-11
tags: [学习, PostgreSQL, 数据库]
status: active
---
# PostgreSQL学习记录

个人知识库的第一版不需要关系数据库。只有当索引需要多进程共享、复杂过滤或更大数据规模时，才考虑 PostgreSQL 与 pgvector。

迁移前先保持 Retriever 合同稳定，再验证批量写入、索引创建和真实查询计划。相关取舍记录在 [[向量索引迁移]]。

