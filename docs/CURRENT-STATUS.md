# 项目当前状态

核对日期：2026-09-16。范围：代码、配置、训练留档，以及本轮实际执行的离线接口合同检查。

## 当前产品范围

- Python FastAPI 只读知识服务：Markdown／Frontmatter／标签／双向链接解析、增量向量索引、搜索、问答、关联发现和原笔记定位。
- 当前索引为 JSON 快照＋内存检索；pgvector 是后续演进方向。
- 工具为 search_notes、read_note、find_related_notes，不支持自动创建、修改或删除笔记。
- 查询规划器接入代码存在，配置默认关闭；有 Schema 和路径约束，不代表现有 LoRA 已在运行实例启用。
- 来源存在检查不等于每句话均经过事实核验。
- 成长方向推荐等内容属于方案增量，不是已完成产品功能。

## 训练状态

2026-09-14 已完成 Qwen2.5-3B 查询规划 LoRA 训练并有 Adapter 与训练记录。数据为 70／8／4 的训练、验证和测试划分。
当前尚无已确认的同环境基座／Adapter 生成收益对照，不能宣称准确率或业务提升。
[训练留档](../artifacts/training/2026-09-14/query-planner/README.md)优先于早期方案中的“尚未训练”描述。

## 接口验收与作品材料

[接口验收材料](validation/api/README.md)包含 OpenAPI、请求集合、断言脚本、Excel 测试表及原始结果。
本轮 10 项离线接口合同测试通过：真实 FastAPI 路由＋替身检索和模型，未访问私人 Vault，也未调用付费模型。
1 项真实模型问答待测。替身测试不证明真实检索质量、生成质量或线上性能。
ProcessOn／Apifox 客户端操作尚未验证；文件生成不等于本人已经使用这些软件。

## 目录用途

- app/：服务实现；tests/：功能测试。
- sample_vault/：公开虚构示例。
- training/query_planner/：数据、训练与评测入口。
- artifacts/training/：已有训练证据与最终 Adapter。
- docs/validation/api/：本轮验收材料。
- 个人知识库问答和成长方向推荐平台/：方案材料；注意已有与规划能力的区分。
- docs/superpowers/：历史方案，不作为当前功能清单。

## 本次整理

已修正训练说明的旧状态；临时测试目录和重复 checkpoint 移到仓库外归档。源码、最终 Adapter、训练数据、日志及小样本局限说明保留。
详见 [整理记录](CLEANUP-2026-09-16.md)。
