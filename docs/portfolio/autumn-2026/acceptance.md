# 秋招增量验收记录

日期：2026-09-27。开发基线 6a094d8，原开发分支 codex/autumn-career。现已按用户要求同步至项目主目录（main，迁移前 HEAD 26df8c8），改动未提交、未推送。以下开发阶段记录保留，主目录迁移验证见文末。

## 自动验证

所有命令均在本轮工作区执行，使用现有 .venv。无新增运行时依赖。

| 检查 | 实际结果 |
| --- | --- |
| 原有 index/knowledge/config/API 基线 | 21 项通过 |
| K1：test_lexical、test_hybrid、test_source_location、test_index、test_knowledge、test_config | 34 项通过；含 12 个固定向量排序案例 |
| K2：test_career、test_demo、test_api，加受影响 lexical/source_location/knowledge | 29 项通过 |
| K3：test_autumn_demo_report | 1 项真实离线 CLI 集成通过 |
| 审查修复：test_demo、test_api、test_autumn_demo_report | 12 项通过，包含新增的配置隔离回归 |
| 三个自动验收场景 | 全部 HTTP 200，recognized/with_evidence 为 5/4、4/1、4/0；脚本返回 0 |

以上运行存在重叠，最终唯一相关测试数为 54，基线不另加。新增能力先观察缺少实现导致失败；正文过滤和 Windows 网络隔离测试的失败原因已修正并通过。未默认运行全项目测试。

## 浏览器交互

使用内置浏览器真实打开本地离线服务，并已验证：

- 公开虚构数据、词法检索、无生成模型的模式提示。
- 空输入提示；AI 示例自动填入后提交，5 项识别、4 项有资料。
- 从 FastAPI 资料来源打开原文对话框，内容与实际公开笔记一致。
- 点击下载 Markdown 后，实际生成 C:\Users\35029\Downloads\career-evidence.md；浏览器下载事件监听超时，但文件已落盘。统一 Windows CRLF/浏览器 LF 后，与 ai-development.md 全文一致，SHA-256 为 e657ec9bb59e6b49d80f14bf20beb89555f9c0cbc7d47933e88ccf9ddf831e06。
- 数据处理示例返回 4 项识别、0 项资料，并明确提示未找到记录；前后端示例返回 4 项识别、1 项资料。
- 原有 RAG 查询返回 5 条来源，摘录回答明确以“离线证据摘录，未调用生成模型”开头。
- 390 px 视口检查已执行；可用内容宽度 375 px（含滚动条差异），scrollWidth 与 clientWidth 相等，未横向溢出；已查看截图。
- 仅停止本轮创建的服务进程以验证真实连接失败：页面提示失败、操作按钮恢复、旧报告下载禁用；知识库查询按钮保持可用。

截图仅在工具中检查，不宣称另存为本地截图文件。浏览器检查与 pytest 计数分别记录。

## 数据与模型边界

- 使用仓库 16 篇公开虚构笔记，没有添加、改写或读取私人 Vault。
- demo 测试比较运行前后样例文件 SHA-256；禁止真实模型客户端和 httpx 网络传输，外部 socket 连接也被阻止。
- Windows asyncio 内部需要本地 socket pair，测试允许此本机事件循环通信；不因此声称进行了操作系统网络抓包。
- demo 未写 data/index.json；真实聊天与 Embedding 未运行，LoRA 未启用、未重训。
- 未执行可选真实 Embedding 对照；固定向量排序测试不能证明模型召回提升。
- 旧 /health 合同、Source 旧构造和 API 路径保持兼容；生产默认 vector。

## 实施取舍

1. 复用现有虚拟环境，在已有忽略目录下创建隔离工作区；Windows 原生 ledger 替代额外脚本工具。开发阶段使用隔离工作区；迁移后后续 Agent 使用项目主目录。
2. 按用户要求只做相关验证；其代价是未重新验证不相关模块。
3. 来源定位测试单独放入 test_source_location.py，避免改写旧 fixture。
4. 保留未提交代码与执行 ledger，不自动合并、推送或发布；这是开发阶段状态；本轮已按用户指令将改动同步回主目录。

## 独立审查

独立审查发现 1 项 Important，无 Critical：导入 demo 时，app.main 模块级 app=create_app() 提前加载生产 Settings，使无效的生产配置阻断离线演示。

已新增子进程回归：环境变量 PLANNER_ENABLED 无效、当前目录 .env 的 PLANNER_TIMEOUT_SECONDS 无效时，修复前导入 demo 抛出 ValidationError；将配置解析延后到实际 lifespan 启动后，离线入口成功启动且 capabilities 正确。修复后 12 项 demo/API/报告相关测试全部通过；实际网页已验证重新启动和交互恢复。

审查另核对了失败脚本：通过真实 demo 路由注入 503，三个场景记录 passed=false，并生成失败 JSON、Markdown 和 run.json。没有通过错误响应伪造绿色报告。

未发现需后置的 Minor 项。K1–K3 已完成。

## 本机预览

修复后的本地预览已在 127.0.0.1:8011 运行，仅绑定回环地址；启动窗口隐藏。开发阶段启动器为 27724；迁移后预览进程状态见文末记录。服务失效时按演示入口的一条命令重启即可；没有发布到外网。

## 2026-09-27 主目录迁移

已按用户明确要求将 34 个升级文件同步至 C:\Users\35029\Documents\GitHub\个人知识库。迁移前主目录干净，HEAD 26df8c8 相对开发基线仅新增方案文档；相同方案保留，无代码冲突。被替换文件备份和迁移清单位于 .codex_artifacts/migrations/autumn-career-20260927-125512/。原隔离工作区保留，未删除，也未创建提交或推送。

在主目录运行 tests/test_demo.py、tests/test_api.py、tests/test_autumn_demo_report.py：12 项通过；这些是迁移回归，不叠加到前述 54 个唯一测试数。三份报告已从主目录重新生成，退出 0。已确认加载的模块路径为项目主目录下 app/demo.py。

预览已从原隔离工作区切换到主目录，地址仍为 http://127.0.0.1:8011/；启动器 PID 33504，实际服务进程与日志保存于 .codex_artifacts/migrations/main-demo/。capabilities 已确认 demo=true、answer_mode=extractive。后续直接在主目录修改、启动即可。
