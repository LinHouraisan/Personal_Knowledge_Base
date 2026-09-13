# Obsidian 个人知识库 RAG 系统设计

## 目标

构建一个面向 Obsidian Markdown Vault 的本地知识检索与问答服务。系统读取笔记、建立可增量更新的索引，通过 LangChain Agent 完成检索、阅读和关联发现，并为每条回答提供可核对的来源。用户可以从检索结果直接唤醒 Obsidian 并定位到对应笔记。

项目首先服务于真实的个人知识管理工作流，同时提供脱敏示例 Vault，便于公开演示和自动化测试。

## 核心边界

- Agent 默认且永久保持只读，只能检索、读取、总结和提出整理建议。
- 系统不实现创建、修改或删除笔记的工具。
- 所有内容编辑由 Obsidian 或其他成熟写作工具完成。
- 真实 Vault 路径、模型密钥和本地索引不提交到 Git。
- 回答必须携带来源；没有足够证据时明确说明无法从知识库确认。
- 不伪造历史提交、使用时长、模型效果或私人数据。

## 技术路线

- Python 3.11
- FastAPI 提供 API、Swagger 文档与本地演示页面
- LangChain 负责模型接入、工具定义和 Agent 编排
- OpenAI-compatible 聊天接口，可接 DeepSeek 或本地模型
- Ollama `bge-m3` 作为默认 Embedding 服务
- JSON 保存可再生成的演示索引，进程启动后载入内存
- Retriever 协议隔离索引实现，为后续替换 pgvector 或其他向量库保留边界

## 系统结构

```text
Obsidian Vault
  └─ Markdown Scanner
       ├─ Frontmatter / Tags
       ├─ [[Wikilinks]]
       └─ Paragraph Chunks
              ↓
       Embedding Provider
              ↓
       JSON Index → In-memory Retriever
              ↓
FastAPI → LangChain Read-only Agent
              ↓
Answer + Evidence + Obsidian URI
              ↓
Local Web UI → 在 Obsidian 中打开
```

## 组件设计

### 配置

环境变量提供 Vault 路径、Vault 名称、聊天模型地址、Embedding 地址、模型名和索引路径。仓库提供 `.env.example`，但不提交实际 `.env`。

默认读取仓库内的 `sample_vault`，使首次启动不依赖私人资料或在线模型即可检查扫描和检索流程。

### Markdown 扫描器

扫描 Vault 中的 `.md` 文件，排除 Obsidian 配置目录、回收站、附件目录和用户配置的忽略目录。每篇笔记提取：

- 标题与相对路径
- YAML Frontmatter
- 标签
- `[[双向链接]]`
- 正文段落
- 文件修改时间与内容哈希

内容哈希用于识别新增、修改和删除的笔记，避免每次重建全部 Chunk。

### Chunk 与索引

按标题层级和段落切分笔记，保留笔记路径、标题、标签和相邻标题作为元数据。Embedding 调用与文件读取放入异步线程边界，避免阻塞 FastAPI 事件循环。

JSON 只负责持久化可再生成的演示索引。服务启动后将向量和元数据载入内存，查询阶段不反复读取文件。索引通过临时文件写入并原子替换，避免中断时留下半份数据。

检索层暴露稳定的 Retriever 接口，API 与 Agent 不依赖 JSON 格式。将来迁移 pgvector 时只新增 Retriever 实现，不修改调用合同。

### 知识关系

根据 `[[双向链接]]` 建立轻量关系图。检索结果可向一跳关联笔记扩展，再根据向量相关度和标签重合度排序，用于发现直接命中之外的上下文。

### 只读 Agent 工具

Agent 只注册以下工具：

- `search_notes(query, top_k)`：检索相关 Chunk，并返回来源和分数。
- `read_note(path)`：读取指定 Vault 内笔记，路径必须通过根目录边界检查。
- `find_related_notes(path)`：根据双向链接和标签返回关联笔记。

工具输出是回答证据。最终响应同时返回结构化 `sources`，而不是只依赖模型在正文中生成引用。Agent 没有命中证据或没有调用检索工具时，接口返回无法确认，不接受无来源结论。

### Obsidian 定位

每条笔记结果根据 Vault 名和相对路径生成 URL 编码后的 URI：

```text
obsidian://open?vault=<vault>&file=<relative-note-path>
```

本地演示页面在每条引用旁展示“在 Obsidian 中打开”链接。点击后由操作系统的 Obsidian 协议处理程序唤醒客户端并定位笔记。

同时提供只负责生成和打开上述 URI 的 Windows CLI 命令，作为浏览器限制自定义协议时的备用入口。自动化测试只验证 URI 编码和启动调用，不在测试期间真正唤醒桌面程序。

### API 与演示页面

- `GET /health`：返回服务、Vault 和索引状态。
- `POST /index/rebuild`：扫描 Vault 并增量更新索引。
- `GET /search`：返回匹配片段、元数据和 Obsidian URI。
- `POST /chat`：执行只读 Agent，返回回答、来源和执行状态。
- `GET /notes/{note_id}`：返回单篇笔记的脱敏读取结果。
- `GET /`：本地搜索和问答页面，展示引用与 Obsidian 打开按钮。

API 不提供写入、上传或删除接口。

## 示例 Vault

仓库内置约 15 至 20 篇相互关联的虚构笔记，覆盖项目日志、AI 学习、工程实践、读书摘记和复盘记录。内容使用明确的日期、标签和双向链接形成可检索关系，但不冒充用户的真实历史资料。

示例数据需要覆盖以下演示：

- 通过语义问题命中不同措辞的笔记。
- 从一篇项目笔记发现其关联的技术决策。
- 点击结果唤醒 Obsidian 并定位文件。
- 对知识库不存在的问题拒绝编造答案。

## 错误处理与安全

- 所有文件访问都校验解析后的绝对路径必须位于 Vault 根目录内。
- 忽略隐藏目录、附件和非 Markdown 文件。
- 上游模型或 Embedding 不可用时返回明确错误，不退化为伪造答案。
- 索引损坏时健康检查标记未就绪，并提示重建。
- 日志记录接口、状态、耗时和命中文档数量，不记录笔记正文、Prompt、回答正文或密钥。
- Obsidian URI 仅由配置的 Vault 名和已扫描的相对路径生成。

## 测试策略

测试使用确定性的 Fake Embedder 和 Fake Chat Model，不访问网络、不读取真实 Vault，也不唤醒桌面应用。

最小测试范围：

- Markdown、Frontmatter、标签和双向链接解析。
- Chunk 元数据与内容哈希。
- 增量索引的新增、修改和删除。
- 向量检索与关联笔记扩展。
- 路径穿越拦截。
- Obsidian URI 的中文、空格和嵌套路径编码。
- Agent 无证据拒答和结构化来源返回。
- FastAPI 健康检查、搜索与问答接口。

## 明确不做

- Obsidian 插件和编辑器内嵌聊天面板。
- 笔记创建、修改、删除或自动整理。
- 多用户、权限系统和公网部署。
- 生产级向量数据库、任务队列和监控平台。
- 使用真实私人笔记作为仓库演示数据。

## 完成标准

1. 克隆仓库后按照中文 README 可以启动服务并打开本地页面。
2. 示例 Vault 能完成扫描、增量索引、搜索和关联发现。
3. 搜索结果和问答来源均能生成正确的 Obsidian 定位链接。
4. Agent 全程只读，无写笔记能力。
5. 没有知识库证据时不生成确定性答案。
6. 离线测试覆盖核心解析、检索、安全边界和 API。
7. README 包含架构、演示步骤、隐私说明、局限性和可核验的简历表述。
