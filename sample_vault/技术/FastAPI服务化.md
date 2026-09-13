---
created: 2026-09-07
updated: 2026-09-11
tags: [FastAPI, API, 工程]
status: active
---
# FastAPI服务化

FastAPI 提供健康检查、索引重建、搜索、问答和按 ID 读取笔记接口。Swagger 用来核对接口，本地页面承担日常查询入口。

阻塞的文件扫描与 JSON 持久化放到工作线程，避免占用事件循环。访问日志只记录路径、状态、耗时和来源数量，不记录问题、笔记正文或回答内容。

