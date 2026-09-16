# Obsidian 个人知识库 RAG

## 当前状态与材料入口

请先阅读 [项目当前状态](docs/CURRENT-STATUS.md)，区分已实现能力、已完成训练、历史评测和未验证效果。

- [接口集合、Excel 测试表与执行记录](docs/validation/api/README.md)

这是一个面向 Obsidian Markdown Vault 的只读知识检索与问答服务。它解析 Frontmatter、标签和 `[[双向链接]]`，建立可增量更新的向量索引，通过 LangChain Agent 检索证据，并让用户从来源卡片直接回到 Obsidian 原笔记。

系统只提供搜索、总结、关联发现和整理建议。创建、修改和删除笔记仍由 Obsidian 或其他成熟写作工具完成。

## 核心能力

| 能力 | 实现 |
| --- | --- |
| Obsidian Vault 解析 | Markdown、YAML Frontmatter、标签、双向链接和反向链接 |
| 增量向量索引 | 按文件哈希复用未变化 Chunk，只重新 Embedding 变化笔记 |
| LangChain Agent | `search_notes`、`read_note`、`find_related_notes` 三个只读工具 |
| 幻觉约束 | 没有工具证据时丢弃模型结论，API 独立返回结构化来源 |
| Obsidian 定位 | 为每条来源生成 `obsidian://open` URI，支持中文和嵌套路径 |
| FastAPI | 健康检查、索引重建、搜索、问答、笔记读取及 Swagger 文档 |
| 隐私隔离 | 真实 Vault、密钥、生成索引和问题正文不进入仓库或访问日志 |

## 架构

```text
Obsidian Vault
  → Markdown / Frontmatter / Tags / Wikilinks
  → Chunk + Embedding
  → JSON Snapshot → In-memory Retriever
  → LangChain Read-only Agent
  → Answer + Structured Sources
  → obsidian://open → 原笔记
```

JSON 只在加载和重建时发生 I/O，查询阶段使用内存记录。API 与 Agent 只依赖 Retriever 接口；数据规模增长后可以新增 pgvector 实现，而无需修改调用合同。

## 快速开始

需要 Python 3.11+、Obsidian，以及用于向量化的 Ollama。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
Copy-Item .env.example .env
ollama pull bge-m3
```

在 `.env` 中填入新生成的聊天模型密钥。不要复用曾经粘贴到聊天、截图或提交记录中的密钥。

```dotenv
VAULT_PATH=sample_vault
VAULT_NAME=个人知识库示例
INDEX_PATH=data/index.json

CHAT_BASE_URL=https://api.deepseek.com
CHAT_API_KEY=<your-new-key>
CHAT_MODEL=deepseek-chat

EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1
EMBEDDING_API_KEY=<not-required-for-ollama>
EMBEDDING_MODEL=bge-m3
```

启动服务：

```powershell
.\.venv\Scripts\uvicorn.exe app.main:app --reload
```

第一次使用先建立索引：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/v1/index/rebuild
```

然后访问：

- 本地页面：`http://127.0.0.1:8000/`
- Swagger：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/health`

## 使用自己的 Vault

只修改本地 `.env`：

```dotenv
VAULT_PATH=D:/Notes/MyVault
VAULT_NAME=MyVault
```

`VAULT_NAME` 必须与 Obsidian 中显示的 Vault 名称一致。真实目录不会被复制到项目；扫描器只读取 `.md`，并忽略 `.obsidian`、`.trash`、`attachments`、隐藏目录和非 Markdown 文件。

## 定位到 Obsidian 原笔记

搜索和问答结果都包含“在 Obsidian 中打开”链接。浏览器点击自定义协议受限时，可以使用备用命令：

```powershell
.\.venv\Scripts\obsidian-kb.exe open --vault "MyVault" --file "项目/RAG 方案.md"
```

命令只生成并交给操作系统打开 `obsidian://open` URI，不直接读取或修改笔记。

## API 示例

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/v1/search?q=为什么选择本地Embedding&top_k=3"

Invoke-RestMethod -Method Post `
  -ContentType "application/json" `
  -Body '{"question":"如何避免知识库回答编造内容？"}' `
  http://127.0.0.1:8000/v1/chat
```

Agent 的三项工具均为只读。没有调用工具或没有找到证据时，接口返回 `status=no_evidence`，不会把模型自由生成的内容当作知识库事实。

## 测试

测试使用 Fake Embedder 和 Fake Agent，不访问网络、私人 Vault 或桌面应用：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app
```

## 示例数据与隐私

`sample_vault` 是互相关联的公开虚构笔记，用于演示项目日志、学习记录、技术决策和每周复盘的检索关系。日期属于示例语料，不代表真实个人笔记或仓库历史。

以下内容被 `.gitignore` 排除：

- `.env` 和模型密钥
- `private_vault/` 私人资料
- `data/` 生成索引
- Python 虚拟环境和缓存

访问日志只记录请求方法、路径、状态、耗时和来源数量，不记录查询参数、笔记正文、Prompt 或回答正文。

## 已知边界

- JSON 向量索引适合个人规模和工程演示，不是生产级向量数据库。
- 首次重建依赖可用的 Embedding 服务；聊天问答依赖配置的聊天模型。
- Agent 不修改笔记，也不替代 Obsidian 的编辑、版本管理和插件生态。
- 实际召回质量应由真实语料评测决定，仓库不预设效果提升数字。

## 简历表述

> 面向 Obsidian Markdown Vault 设计并实现只读个人知识库 RAG 系统，解析 Frontmatter、标签与双向链接，支持增量向量索引、LangChain 工具调用、结构化来源返回及 Obsidian 原笔记定位；通过证据门控限制无来源回答，并将检索接口与 JSON 存储解耦，为后续迁移 pgvector 保留扩展边界。
