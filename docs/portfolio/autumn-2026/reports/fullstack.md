# 岗位关键词证据对照

方法：keyword_evidence_v1（规则匹配，无模型评审）
已识别关键词的资料覆盖率：25.0%；资料命中 1/4

## React

状态：当前知识库未找到相关记录
命中别名：react
岗位原句：使用 React、TypeScript 开发页面，能编写 SQL 并使用 PostgreSQL。
建议：可通过以下交付物补充记录：一个有加载和失败状态的组件示例。


## TypeScript

状态：当前知识库未找到相关记录
命中别名：typescript
岗位原句：使用 React、TypeScript 开发页面，能编写 SQL 并使用 PostgreSQL。
建议：可通过以下交付物补充记录：类型约束与编译检查记录。


## SQL

状态：当前知识库未找到相关记录
命中别名：sql
岗位原句：使用 React、TypeScript 开发页面，能编写 SQL 并使用 PostgreSQL。
建议：可通过以下交付物补充记录：一组查询及执行结果。


## PostgreSQL

状态：找到相关资料
命中别名：postgresql
岗位原句：使用 React、TypeScript 开发页面，能编写 SQL 并使用 PostgreSQL。
建议：核对已有记录并补齐：表结构、索引和查询计划记录。

- 来源：学习/PostgreSQL学习记录\.md
  分块：9cc912a66e6e4dc0d1af；标题：PostgreSQL学习记录
  摘录：\# PostgreSQL学习记录  个人知识库的第一版不需要关系数据库。只有当索引需要多进程共享、复杂过滤或更大数据规模时，才考虑 PostgreSQL 与 pgvector。  迁移前先保持 Retriever 合同稳定，再验证批量写入、索引创建和真实查询计划。相关取舍记录在 \[\[向量索引迁移\]\]。

## 使用边界

- 仅提取 12 项有限词表关键词，不能完整理解岗位要求；请核对原句，尤其是否定或可选要求。
- 关键词资料命中不等于个人能力、项目经历或录用概率；未找到记录不代表不会。
- 结果未经过人工核验；建议来自 keyword\_evidence\_v1 固定模板。
