# 个人知识库秋招演示入口

本轮新增岗位关键词证据对照、可选混合检索及无密钥离线演示。复用 FastAPI、Pydantic、现有检索接口和原生 HTML/JavaScript，没有新增运行时依赖。

## 直接查看报告

- [AI 应用开发](../../../artifacts/portfolio/autumn-2026/ai-development.md)：5 项识别，4 项有资料。
- [前后端开发](../../../artifacts/portfolio/autumn-2026/fullstack.md)：4 项识别，1 项有资料。
- [数据处理与标注](../../../artifacts/portfolio/autumn-2026/data-workflow.md)：4 项识别，0 项有资料。
- [原始执行结果](../../../artifacts/portfolio/autumn-2026/run.json)
- [实际验收记录](acceptance.md)
- [面试说明与简历事实](interview-notes.md)

以上来自 16 篇既有公开虚构笔记，资料命中数不代表个人能力。所有 JSON 和 Markdown 都由真实离线演示路由生成。

## 一条命令启动

在项目根目录执行（已有 .venv，无需另装 Obsidian、Ollama 或申请密钥）：

~~~powershell
.\.venv\Scripts\python.exe -m app.demo --port 8011
~~~

浏览器打开 http://127.0.0.1:8011/。端口被其他程序占用时改用 --port 8012；不要关闭未知服务。

本机项目目录：C:\Users\35029\Documents\GitHub\个人知识库。2026-09-27 已按用户要求将本轮代码、测试和报告同步回此主目录；后续在这里运行即可。改动尚未提交或推送，原隔离工作区保留作为备份。

自动重新生成三个场景的报告：

~~~powershell
.\.venv\Scripts\python.exe -m tools.autumn_demo_report --out artifacts/portfolio/autumn-2026
~~~

退出 0 表示三个场景通过合同核对；失败返回非零并保留场景状态。run.json 中 model_evaluation=not_run，不填写虚构准确率。

## 三分钟演示路线

1. **0:00–0:30**：展示页面“公开虚构数据 · 词法检索 · 无生成模型”，解释这是可独立运行的工程演示。
2. **0:30–1:10**：填写 RAG，检索并查看原文；指出来源的标题、路径、分块标识。
3. **1:10–2:10**：选择 AI 开发示例，对照要求关键词与已有资料；Python 未找到记录，不能据此说用户不会 Python。打开一个来源，再下载 Markdown。
4. **2:10–2:40**：切到数据处理示例，展示未记录项及固定实践建议；有限词表只覆盖已识别项。
5. **2:40–3:00**：展示 run.json、验收记录，解释生产默认 vector、可选 hybrid，以及尚未做真实模型效果对照。

## 运行与证据边界

- 生产路径保留原有生成模型与向量接口；RETRIEVAL_MODE 默认 vector，hybrid 明确选择后才使用 RRF。
- RRF 只决定排序，Source.score 仍为原余弦值；离线词法来源的 score=null，不显示可信度百分比。
- 岗位对照不调用模型，只支持 12 项有限词表；否定、可选要求必须结合原句理解。
- 笔记只读；演示固定 sample_vault，不读取真实 Vault、不写 data/index.json、不训练模型。
- 查询规划 LoRA 是既有工程记录；本次未启用或重训，也未验证它带来效果提升。
