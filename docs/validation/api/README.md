# 项目辅助材料使用说明

## 已完成内容

1. TRPG 流程图已归入另一仓库的 docs/portfolio/product/，本目录专用于知识库接口。
2. 知识库接口：从现有 FastAPI 应用导出 OpenAPI，另提供 Postman v2.1 请求集合，可用于导入 Apifox。
3. Excel 测试表：记录 10 条已执行的离线接口合同测试和 1 条待完成的真实模型问答，含筛选、冻结表头、状态下拉和动态计数。

## 测试范围

已执行的是现有 FastAPI 路由，知识服务和模型使用替身。这样可以验证参数约束、状态码及返回结构，不证明真实向量检索或模型回答质量。
没有访问私人 Vault、读取项目 .env 或调用付费模型。
API-09 是特定无证据替身响应的合同测试，不能直接用同一句问题在真实模型中期待相同结果。
Excel 的毫秒数是进程内隔离测试耗时，不能作为线上性能指标。

## Apifox

1. 项目设置 → 手动导入 → 选择 OpenAPI，导入“知识库_OpenAPI.json”。
2. 也可选择 Postman 导入“知识库接口验收.postman_collection.json”。建议在单独项目中操作，避免与原接口合并造成用例丢失。
3. 设置 baseUrl 为实际服务地址，默认 http://127.0.0.1:8000。
4. 官方导入说明注明 Postman 导入只包含接口，因此不要假定所有同路径请求变体、断言和测试套件都会完整迁移。若被合并，按 Excel 用例重新保存不同参数为接口用例。
5. 后置断言参考“接口断言脚本.md”，Apifox 支持 Postman 风格脚本，但本交付没有在 Apifox 客户端导入运行。
6. 正常搜索需要可用索引和 Embedding，真实问答还需要配置聊天模型。无服务时不要将连接失败误记为项目逻辑缺陷。
7. 在客户端实际运行后，将结果填写到新的复测记录，保留当前离线记录。

## 简历表述

现在可说明：在 AI 辅助下整理系统流程图、接口测试集合和 Excel 验证记录，完成 10 项离线接口合同检查，覆盖参数校验、异常响应与来源结构。
经过本人阅读、导入、修改和操作确认后，可按实际程度写使用相应工具整理流程、调试接口和维护测试记录。
文件生成不证明本人已熟练使用 ProcessOn、Apifox 或 Excel 高级功能。真实模型验收仍待执行。

## 来源

- TRPG：README.md、electron/src/main/paths.ts、services/ai-api/app/storage.py、services/ai-api/compose.yml，以及已有状态与恢复材料。
- 知识库：app/main.py、app/models.py；原始执行记录见本目录“接口执行结果.json”；原项目入口和参数定义保持不变。
- Apifox 导入：https://apifox.com/help/api-manage/import-api/intro/
- Apifox 脚本：https://docs.apifox.com/scripts
- draw.io 打开文件：https://www.drawio.com/docs/manual/open-diagram-file/


## 文件导航

- [OpenAPI](知识库_OpenAPI.json)
- [请求集合](知识库接口验收.postman_collection.json)
- [Excel 测试表](知识库接口测试记录.xlsx)
- [断言脚本](接口断言脚本.md)
- [原始执行结果](接口执行结果.json)
