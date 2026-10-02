# Personal Knowledge Demo Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 用公开虚构笔记完成查资料、做复盘、定下一步、反馈复查和双击启动；统一整理文档并清理重复产物。
**Architecture:** 复用 FastAPI、现有只读知识服务与原生页面。复盘读取笔记中显式的状态和日期；演示不调用模型。用户主动保存的反馈留在浏览器本地，可导出；不写回笔记。
**Tech Stack:** Existing Python / FastAPI / Pydantic; HTML / CSS / JavaScript; no new dependencies.
**Spec:** 本对话已确认的个人知识库方案及用户本轮“开始施工”指令；用户授权自行编写全部演示案例，不接入私人笔记。

## Global Constraints
- 保留原来的真实模型问答、搜索、训练代码与训练产物；默认演示仅使用 sample_vault。
- 三个主入口：查资料、做复盘、定下一步。反馈为次级入口。
- 每个复盘条目和行动显示来源。计划不算完成；已解决事项不再沿用旧待办。
- 文档统一到 docs；虚构 Markdown 笔记是程序样例数据，保留 sample_vault。
- 沿用现有环境，在目标目录的 codex/personal-demo 分支执行；不增加工作副本。只验证本次相关区域。

## Review Focus
- 日期缺失、无匹配资料：说明范围，不填充结论。
- 相同事项后续已完成：不把旧问题当作当前问题。
- 目标不属于所选主题：不跨目标给建议。
- 浏览器保存失败：不能显示保存成功；复查保留原结果。
- 清理不可越出项目；训练内容按哈希确认保留。

## Tasks and progress
- [x] Task 1: tests/test_reflection.py; app/reflection.py; app/knowledge.py; app/main.py. Add GET /v1/workspace and POST /v1/reflection. Check filters, evidence, chronological status, goal actions and empty results against actual note files.
- [x] Task 2: sample_vault examples; app/static/index.html + style.css + app.js. Three views, note reading, feedback storage/export and recheck. Check real browser flows and small viewport.
- [x] Task 3: app/launch.py and 启动演示.cmd. Keep fixed local demo, reusable port and browser launch. Check startup and actual HTTP responses.
- [x] Task 4: consolidate docs, preserve AI training, remove verified duplicates/caches. Run targeted tests and inspect final tree; record moves and checks here.

## Evidence and decisions
- Baseline: tests/test_demo.py + tests/test_api.py => 11 passed.
- 本轮按用户明确施工指令直接执行，不再次要求确认方案。使用原目录新分支，满足清理现场与可直接运行要求。
- 反馈采用浏览器本地保存和文件导出，避免为单人 demo 新增数据库。

- 新增复盘接口：7 项用例由 404 失败转为通过；相关 API 合计 16 项通过。增加样例后 demo/API/reflection 共 18 项通过。
- 独立审查发现 3 项：窄屏反馈入口隐藏、启动超时残留进程、复查前资料未刷新。已修复入口和刷新流程；启动清理已用真实子进程复现失败后修复。

## 本轮完成与验证

- 最终局部检查：`python -B -m pytest -p no:cacheprovider tests/test_reflection.py tests/test_demo.py tests/test_api.py tests/test_launch.py tests/test_autumn_demo_report.py -q`，21 项通过，退出码 0。不是全项目测试，不与前面的阶段检查叠加计数。
- `node --check app/static/app.js` 通过。当前文档本地链接检查通过，历史设计里的规划路径不作为现行入口。
- 浏览器实测：RAG 查询返回来源；学习复盘、项目复盘、按目标定行动均正常；来源可打开原文；反馈保存后刷新仍保留；切换复查方式后原结果与新结果同时保留。
- 桌面 1280×900 和窄屏 390×844 已检查截图。窄屏有效宽度为 375，页面内容宽度同为 375，无横向溢出；改进记录入口可见。检查后已恢复默认窗口尺寸。截图仅在工具中检查，未另存本地图片。
- 浏览器错误记录为空。内置浏览器已点击反馈导出，但下载事件未返回路径，常用下载目录未找到文件，故不将文件落盘计入已验证能力。导出代码保留；默认双击入口使用系统浏览器。
- 本轮没有调用真实模型、重新训练、读写私人笔记，也没有提交或推送改动。

## 目录整理与恢复信息

- 文档统一在 `docs/`；根目录旧说明改为 `docs/technical-guide.md`，新增使用说明、直白升级报告和当前状态。
- 原始 Word／PDF／PPT 已集中到 `docs/archive/original-proposal/`。旧前台报告在 `docs/portfolio/autumn-2026/reports/`。
- 训练代码留在 `training/query_planner/`，模型、原始数据和日志迁移到 `training/artifacts/`。训练说明与原始模型说明移到 `docs/training/`。
- 移动前后对 35 个训练相关文件核对 SHA-256，全部一致，包括最终权重、分词文件、训练数据、日志、配置、训练代码与原始模型说明。旧哈希清单保留原路径和历史含义，不宣称已恢复历史上更早移出的 checkpoint。
- 已调整忽略规则和大文件跟踪路径，保证移动后的最终模型与原始训练数据可继续正常跟踪。
- 旧开发副本未提交的改动已保存在 Git stash `7f8c6f216b65609f006e05ef47c03b18949fe3ee`；需要时可先用 `git stash show --stat 7f8c6f216b65609f006e05ef47c03b18949fe3ee` 查看。主目录原有历史仍保留。
- 旧开发副本中的训练内容与主目录核对一致，已安全移除该副本。先解除指向主目录运行环境的目录链接，主目录 `.venv` 保留。
- 删除旧迁移备份、临时草稿、测试缓存、Python 缓存和生成的安装元数据。全部清理目标都已检查位于本项目内部。
- 最终根目录仅留应用、检查代码、工具、虚构笔记、训练内容、文档、运行环境、运行日志、必要配置和双击启动入口。
