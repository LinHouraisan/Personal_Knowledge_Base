# 个人知识库秋招冲刺技术实施方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking. 默认一个 agent 连续完成，避免为每个小任务重复派发和重复审查。
>
> **执行指令（可直接复制）：** 请执行本文件的首轮范围 K1–K3。核对相关代码后直接实现、运行局部验证并生成可演示交付物。不要让我手工准备笔记、岗位描述、标注、测试或截图。保留当前后端和网页技术，优先零新增依赖；真实模型不可用时自动完成标明离线模式的演示与合同测试，不能伪造模型评测结果。不要启动后置范围、训练、付费资源、推送或发布。

**Goal:** 在现有只读 RAG 上交付可定位来源、可对照岗位关键词证据的完整网页流程，并提供无需密钥、Obsidian 或 Ollama 的离线演示。
**Architecture:** 保留 FastAPI、KnowledgeService、Retriever 和既有问答接口。补充确定性的词法检索组件及可选混合检索；岗位要求采用有限词表提取，资料证据由程序匹配，建议来自版本化模板。既有 HTML 页面增加证据对照区，独立 demo 工厂注入词法检索和摘录回答。
**Tech Stack:** 现有 Python 3.11+、FastAPI、Pydantic、LangChain、pytest、httpx、原生 HTML/CSS/JavaScript；不新增运行时依赖。
**Spec:** 本文第 1–4 节为首轮设计，第 5–7 节为实施计划。用户要求按本文执行后直接实施，不重复发起需求访谈或阶段授权。
**项目根目录:** C:\Users\35029\Documents\GitHub\个人知识库
**编制日期:** 2026-09-25
**事实依据:** 当前源码；方案编制未运行真实模型。本轮不把过去的替身接口测试当作真实问答质量。

## 1. 范围与求职价值

首轮仅 K1–K3：
1. 检索来源带有分块标识和标题，提供可测试的词法候选与混合排序。
2. 粘贴岗位描述后返回“要求关键词—资料证据—建议补充实践”，可导出 Markdown。
3. 一条命令启动公开样例演示，agent 自动完成接口测试、界面检查及材料生成。

对应能力：AI 应用的检索与证据接口；数智化的结构化业务流程；前后端联调；数据处理的规范化、去重和口径说明。

明确后置：React 重写、多租户/RBAC、持久任务队列、pgvector、Spark/Kafka、爬招聘网站、自动投递、自动写笔记、新一轮 LoRA 训练、自由生成的个性化课程推荐、大规模性能压测、每句话语义事实核验。

取舍：岗位对照先做可解释的有限关键词规则，解决无模型、无标注人员也可演示的问题。它不能宣称理解所有 JD、判断个人熟练度或预测录用概率。现有 RAG 与 LoRA 是项目原有能力，本轮增加业务应用和工程证据。

## 2. 当前实现与复用位置

- app/main.py：FastAPI 工厂、/health、/v1/search、/v1/chat、/v1/notes/{note_id}、根网页。
- app/index.py：Retriever Protocol、JsonVectorIndex、增量 Embedding、余弦排序。
- app/knowledge.py：缓存笔记、Source 构建、搜索、关联、只读笔记定位。
- app/models.py：Source、SearchHit、NoteChunk、AgentAnswer 等类型。
- app/vault.py：路径约束、Markdown/Frontmatter/标签解析与 chunk_note。
- app/agent.py：证据门控和生成模型；本轮不改成另一套 Agent 框架。
- app/static/index.html：现有页面，约百行，直接增量修改。
- app/config.py：已有配置；planner_enabled 默认 false，不自动打开 LoRA。
- tests/test_index.py、test_knowledge.py、test_api.py、test_agent.py：复用验证。
- sample_vault：16 篇公开虚构笔记。已有测试固定数量，禁止为演示随意增加或改写这些笔记。
- training/query_planner：保留训练与历史评测，不移动、不重训。

当前限制：Source 没有 chunk_id/heading；无证据门控不等于逐句事实核验；查询规划器训练存在不等于运行实例启用。

## 3. Global Constraints

- 只读访问笔记；新增接口不创建、修改、移动或删除 Obsidian 笔记。
- 不读取用户真实 Vault 来制作公开样例；离线演示显式锁定仓库 sample_vault。
- 不输出或复制密钥；默认不调用付费服务，不下载新模型，不需要用户安装 Obsidian。
- 不新增运行时依赖、不重写前端框架、不迁移数据库；局部模块只为当前功能建立。
- 原有 API 路径和字段保留；新增 Source 字段可选，旧 Source 构造和 FakeService 不应被迫迁移。
- Source.score 仍是原有向量余弦值或 null，不能悄悄替换成 RRF 分数或展示为“可信度百分比”。
- 混合检索保持明确配置且默认沿用 vector；真实质量证据不足时不替用户切换生产策略。
- demo 的词法检索/摘录回答必须在页面、接口元信息和报告中明确标识，不能伪装成真实大模型运行。
- 指标“资料关键词覆盖率”不等于能力匹配度、求职成功率或人工审核结论。
- 不记录 JD、问题、原笔记、回答正文到访问日志；页面用 textContent 渲染不可信文字。
- 缺少模型或 UI 工具不转化为用户手工任务。完成可独立工作，记录未执行项，不冒充已验证。
- 先检查当前 git 状态和相关文件，不覆盖他人修改。不主动提交、推送、部署或自动合并。
- 达到第 6 节后停止；不因个人兴趣继续优化检索、调参或扩展词表。

## 4. 技术设计

### 4.1 可解释词法候选与混合排序

新增 app/lexical.py，供可选 hybrid、离线 demo、关键词证据复用。

公开接口：
~~~python
def query_terms(text: str) -> set[str]: ...
def lexical_score(query: str, chunk: NoteChunk) -> float: ...
~~~

query_terms 算法：
- Unicode NFKC、casefold，去首尾空白。
- 拉丁词提取连续字母数字及内部 +/#/点/下划线/横线，保留 C++、C# 等形式，不做自动语言识别。
- 每段连续中文长度 >= 2 时保留整段和所有相邻二字串；单字不单独作为查询词。
- 返回去重集合；空词集合得分为 0。
- 文本字段同样规范化。词命中采用包含匹配，拉丁纯字母数字词加相邻字母数字边界，避免 SQL 命中 NoSQL。
- 分数 = 4*标题命中比例 + 3*标签命中比例 + 2*路径命中比例 + 正文命中比例；分母为查询词数量。
- 空查询词集合返回 0；同分按 relative_path、chunk.id 排序。此分数是候选排序，不是相关概率。

JsonVectorIndex 新增可选 keyword-only 参数 mode: Literal["vector","hybrid"]="vector"，保留全部旧构造调用。
- vector 分支保留现有余弦排序和 score > 0 的行为。
- hybrid 同时计算词法排序和向量排序，各取前 20 条。
- 用 1/(60 + rank) 的 RRF 相加，rank 从 1 起；每个候选在每个列表只出现一次。
- 合并前用 chunk.id 去重；同融合分按 path/id 稳定排序；返回 top_k。
- SearchHit.score 保留原始 cosine；融合值只是内部排序键，不写成 Source.score。
- 若 Embedding 服务失败，生产模式仍走既有 503，不静默假装真实向量检索成功。
- Settings 增加 retrieval_mode: Literal["vector","hybrid"]="vector"，main 工厂传入；配置名称 RETRIEVAL_MODE。
- .env.example 只补说明，不修改用户 .env。

新增 LexicalRetriever 实现现有 Retriever Protocol：
~~~python
class LexicalRetriever:
    def __init__(self, vault_path: Path): ...
    async def load(self) -> None: ...
    async def rebuild(self) -> IndexStats: ...
    async def retrieve(self, query: str, top_k: int) -> list[SearchHit]: ...
    def ready(self) -> bool: ...
~~~
内部使用 scan_vault/chunk_note 和 lexical_score，提供 chunk_count；load 调用一次 rebuild；不落盘、不 Embedding。IndexStats.embedded=0，removed 按前后笔记集合计算。top_k 沿用 1–20。SearchHit.score 在词法检索器中为词法排序值，但 KnowledgeService 输出 Source.score 必须转换成 null，避免冒充 cosine；以检索器 mode="lexical" 明确识别，其他检索器不强制新增 Protocol 成员。

Source 新增可选字段：
~~~python
chunk_id: str | None = None
heading: str | None = None
~~~
KnowledgeService.search 将命中的 chunk.id/heading 传入 Source；read_note/related 生成的 Source 可保持 null。不迁移旧 JSON 索引，不重写 chunk ID 算法。页面显示相应标题，缺少值时不渲染空占位。

这是来源定位能力，不是逐句事实核验，不显示“已验证正确”。

### 4.2 岗位关键词证据对照

新增 app/career.py。首版词表冻结为 12 项：
- Python：python
- FastAPI：fastapi
- React：react、react.js、reactjs
- TypeScript：typescript、ts（独立单词）
- SQL：sql、结构化查询
- PostgreSQL：postgresql、postgres
- RAG：rag、检索增强生成
- Embedding：embedding、向量化、文本向量
- Agent：agent、智能体
- LoRA：lora、低秩适配
- ETL：etl、数据清洗、数据抽取
- 文本数据标注：数据标注、文本标注

拉丁别名使用相邻字母数字边界并按较长别名先匹配。技能在 JD 中首次出现的顺序作为结果顺序，同技能去重。保留命中别名及所在句子，不根据“了解/精通”推断能力等级，不把“不要求 Java”之类否定句推导成新增要求；首轮方法名称为关键词提取，结果允许用户自行核对原文。

KnowledgeService 新增：
~~~python
def keyword_sources(self, terms: list[str], top_k: int = 3) -> list[Source]: ...
~~~
仅在已加载的公开/已配置 Vault 缓存中搜索，不接受外部路径。用与词表相同的规范化和词边界规则匹配正文；正文确有关键词才算资料证据，只有标题或标签命中不能据此认定有正文证据。对正文合格结果用标题/标签匹配优先、路径稳定排序；一篇笔记仅取最优一个片段。excerpt 截取正文首个命中附近最多 240 个字符，返回可定位的 Source；能从 chunk_note 匹配到分块时填写 chunk_id/heading。保留原文大小写和标点，不把规范化文本作为证据正文；规范化只用于匹配，提取片段时维护原文位置映射或在原文中重新定位，避免 NFKC 长度变化导致错位。无匹配返回空列表；不依赖 Embedding 或 Chat。

在 career.py 定义：
~~~python
class CareerRequest(BaseModel):
    jd_text: str = Field(min_length=1, max_length=12000)
    # before validator strip 空白，之后再做长度验证

class RequirementEvidence(BaseModel):
    skill_id: str
    label: str
    matched_terms: list[str]
    jd_excerpt: str
    status: Literal["evidence_found", "not_recorded"]
    sources: list[Source]
    suggested_action: str

class CareerReport(BaseModel):
    method: Literal["keyword_evidence_v1"] = "keyword_evidence_v1"
    requirements: list[RequirementEvidence]
    recognized_count: int
    with_evidence_count: int
    coverage_ratio: float | None
    limitations: list[str]

def build_career_report(jd_text: str, service: KnowledgeService) -> CareerReport: ...
def career_report_markdown(report: CareerReport) -> str: ...
~~~

before validator 用 @field_validator("jd_text", mode="before") 对 str 做 strip，其余类型交给 Pydantic 验证。字段约束没有“注释即实现”。

新增 POST /v1/career/report：
- 消费 CareerRequest，调用 build_career_report，响应 {"report": CareerReport, "markdown": str}。
- 纯规则与已加载资料匹配，不调用 LLM、不写数据库或笔记。
- 只支持的词表项计入 recognized_count；未识别内容保留在用户输入区，不生成虚假的全面匹配结论。
- 无识别项返回 200、空列表、coverage_ratio=null，并说明支持范围，不报 503。
- 有识别项时 coverage_ratio=with_evidence_count/recognized_count；界面称“已识别关键词的资料覆盖率”，不称“岗位匹配度”。
- not_recorded 文案固定为“当前知识库未找到相关记录”，不是“你不会”。
- evidence_found 只表示出现相关资料，不代表完成过项目或熟练掌握。
- limitations 至少包含有限词表、关键词不等于能力、未人工核验三项说明。

每项技能提供一个确定性 suggested_action 模板：
Python=补一段可运行的数据处理脚本及输入输出；
FastAPI=补一个带输入校验和失败响应的接口及测试；
React=补一个有加载和失败状态的组件示例；
TypeScript=补类型约束与编译检查记录；
SQL=补一组查询及执行结果；
PostgreSQL=补表结构、索引和查询计划记录；
RAG=补问题—来源片段—回答的评测案例；
Embedding=补同集检索对照和实验条件；
Agent=补工具调用参数与失败处理案例；
LoRA=补训练配置与同条件对照，未实测不填收益；
ETL=补清洗、去重及重复运行结果；
数据标注=补标签说明、样例和复核记录。
有证据时文案为“核对已有记录并补齐上述交付物”；无证据时为“可通过上述交付物补充记录”。不生成固定课程时长或能力分数。

### 4.3 网页与零密钥 demo

在原 index.html 增加岗位对照 section：
- 一个 textarea、分析按钮、三个公开虚构 JD 示例按钮、结果表/卡片、Markdown 下载。
- 预设：
  A：“使用 Python、FastAPI 开发 RAG 应用，了解 Embedding 和 Agent。”
  B：“使用 React、TypeScript 开发页面，能编写 SQL 并使用 PostgreSQL。”
  C：“使用 Python 和 SQL 完成 ETL，并整理文本数据标注样例。”
- JD 在当前页面内保留，刷新即丢弃，不加 localStorage、不上传到外部。
- 各表单独立 busy/error 状态，避免现有全局 buttons 禁用逻辑误伤新增区域。
- 所有返回文本用 textContent；下载 Blob 使用纯 Markdown，不插入未经清洗的 HTML。
- 维持现有响应式布局，手机窄屏表格允许横向滚动或卡片布局。
- 来源仍有 Obsidian 链接，额外提供“查看原文”按钮，调用既有 /v1/notes/{note_id} 在页面内展示文本。没有 Obsidian 也能演示。
- 不把 Source.score 显示为置信度百分比。

create_app 新增 keyword-only demo_mode: bool=False，并新增 GET /v1/capabilities：
~~~json
{"demo": false, "answer_mode": "configured_model", "vault_origin": "configured"}
~~~
demo 返回 true、extractive、synthetic。它描述运行方式，不证明模型就绪。既有 /health 返回合同保持不变。

新增 app/demo.py：
- create_demo_app() 显式使用仓库 sample_vault、LexicalRetriever、KnowledgeService。
- 显式构造 Settings(_env_file=None, vault_path=固定样例绝对路径, vault_name="公开虚构演示知识库", index_path=未使用的演示路径)，不读用户 Vault，不覆盖 data/index.json。
- 使用 create_app 的 service/agent 注入点；传入 demo_mode=True。
- ExtractiveDemoAgent.answer 通过词法检索返回原文摘录和来源；无结果返回 no_evidence；回答开头写“离线证据摘录，未调用生成模型”。
- demo 注入 agent，不能在启动或查询时建立真实模型客户端/请求外部服务。
- 页面启动时读取 capabilities，显示永久可见的“公开虚构数据 · 词法检索 · 无生成模型”提示。
- 定义 main() 支持 --port（默认 8011），host 固定 127.0.0.1。通过 uvicorn.run(create_demo_app(), host="127.0.0.1", port=...) 运行。
- 不修改全局配置，不抢占或关闭其他项目服务。

## 5. 执行任务

### K1：检索组件和来源定位

**文件**
- 新建 app/lexical.py、tests/test_lexical.py、tests/test_hybrid.py。
- 修改 app/index.py、models.py、knowledge.py、config.py、main.py、.env.example。
- 增补 tests/test_knowledge.py，只验证新增 Source 字段和词法来源 score=null。
- tests/test_index.py 原有行为必须保持，默认 vector 不改变。

**接口**：第 4.1 节 query_terms/lexical_score/LexicalRetriever；JsonVectorIndex(..., mode="vector")；Source 可选字段。

- [ ] 编写词边界与来源测试，先运行失败：
~~~python
from app.lexical import lexical_score
from app.models import NoteChunk

def test_sql_does_not_match_nosql():
    chunk = NoteChunk(
        id="c1", note_id="n1", title="NoSQL",
        relative_path="NoSQL.md", text="NoSQL", tags=[],
    )
    assert lexical_score("SQL", chunk) == 0
~~~
- [ ] 覆盖：中文连续词、大小写、空词、同分稳定排序、重复 chunk、top_k 上限、空索引、仅词法候选、仅向量候选、两者共同候选。
- [ ] 最小实现词法组件和 hybrid；保持默认 vector 路径、增量重建和旧索引格式。
- [ ] 补充 Source 字段传递，词法 Source.score=null；现有 read/related 的字段允许 null。
- [ ] 用 12 个固定离线排序案例验证 RRF 行为；案例来自临时笔记，不要求用户写样例，不称为真实模型召回提升。
- [ ] 运行局部验证：
~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_lexical.py tests/test_hybrid.py tests/test_index.py tests/test_knowledge.py tests/test_config.py -q
~~~

### K2：岗位关键词证据接口与演示工厂

**文件**
- 新建 app/career.py、app/demo.py。
- 修改 app/knowledge.py 增加 keyword_sources；修改 app/main.py 增加 career/capabilities。
- 新建 tests/test_career.py、tests/test_demo.py。
- 增补 tests/test_api.py：新接口、请求日志边界及旧 Source 可用性。
- 不改 app/agent.py 的真实生成逻辑、不启用 planner。

**接口**：第 4.2 节模型、函数及第 4.3 节工厂。career 只调用公开 KnowledgeService 方法，不直接访问私有缓存字段。

- [ ] 在 test_career.py 的 tmp_path 创建两篇公开测试笔记：“使用 FastAPI 实现只读接口”和“用 SQL 汇总记录”；通过 LexicalRetriever 建立真实 KnowledgeService。
- [ ] 先验证以下行为失败，再实现：
~~~python
report = build_career_report("要求 FastAPI、SQL 和 React。", service)
by_skill = {item.skill_id: item for item in report.requirements}
assert by_skill["fastapi"].status == "evidence_found"
assert by_skill["sql"].status == "evidence_found"
assert by_skill["react"].status == "not_recorded"
assert report.recognized_count == 3
assert report.coverage_ratio == 2 / 3
assert all(item.sources for item in report.requirements if item.status == "evidence_found")
~~~
service 是本步骤创建的已 await service.load() 的实例；固定 skill_id 分别为 python/fastapi/react/typescript/sql/postgresql/rag/embedding/agent/lora/etl/data_labeling。
- [ ] 补测试：重复别名只生成一项；无识别项比例为 null；空白和超长 JD 返回 422；NoSQL 不被当作 SQL；命中片段确实来自笔记且原文不变。
- [ ] 实现固定建议模板、Markdown 导出和 POST 接口，不调用模型。
- [ ] 实现 demo 工厂、摘录式 agent、capabilities；旧 create_app 调用继续工作，旧 /health 字段不变。
- [ ] 使用 TestClient(create_demo_app()) 调用 search/chat/career/report/notes/capabilities；在该测试内禁止外部网络路径，证明零外部请求。
- [ ] 记录 demo 前后 sample_vault 的文件哈希，断言未修改；不得写真实 data/index.json。
- [ ] 运行一次局部验证：
~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_career.py tests/test_demo.py tests/test_api.py -q
~~~

### K3：页面、自动验收与作品交付

**文件**
- 修改 app/static/index.html。
- 新建 tools/autumn_demo_report.py、tests/test_autumn_demo_report.py。
- 新建 docs/portfolio/autumn-2026/README.md、acceptance.md、interview-notes.md。
- 修改 README.md、docs/CURRENT-STATUS.md，区分原有 RAG、此次规则对照、离线演示及未验证效果。
- 输出 artifacts/portfolio/autumn-2026/，不把临时数据塞进训练目录。

**接口**
~~~powershell
# 默认环境已存在时从项目根目录执行
.\.venv\Scripts\python.exe -m app.demo --port 8011
.\.venv\Scripts\python.exe -m tools.autumn_demo_report --out artifacts/portfolio/autumn-2026
~~~
tools/autumn_demo_report.py 使用现有 httpx/FastAPI TestClient 驱动实际 demo 路由，不复制 career 算法或手写假响应。

- [ ] 实现第 4.3 节页面，保留原有搜索/问答；新增样例按钮、独立表单状态、原文查看和 Markdown 下载。
- [ ] 验收脚本依次提交三个固定 JD，保存请求摘要（仅公开样例）、真实响应 JSON、Markdown 清单及 run.json。
- [ ] run.json 包含 mode=synthetic_offline、三个场景的 HTTP 状态/识别数量/资料命中数、代码版本、明确的 model_evaluation=not_run。使用固定样例摘要哈希，不伪造人工评审。
- [ ] 验收脚本返回非零表示场景失败，不让错误报告仅显示绿色。
- [ ] 给脚本写一条离线临时目录集成测试，检查三个 Markdown 文件和 JSON 的真实性，不重复覆盖 career 单元测试。
- [ ] 执行脚本与局部测试；如果本阶段没有改变 K1/K2 的 Python 代码，不重复运行其已通过的全部测试。
~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_autumn_demo_report.py -q
.\.venv\Scripts\python.exe -m tools.autumn_demo_report --out artifacts/portfolio/autumn-2026
~~~
- [ ] agent 自己启动 demo；Windows 后台启动必须隐藏窗口，保存进程标识，只关闭自己启动的进程。
- [ ] 有浏览器工具时自动完成一次真实交互烟测：样例填充→提交→查看来源→下载 Markdown；同时检查空输入、服务失败提示和窄屏。截图仅使用公开样例。
- [ ] 没有可用浏览器控制工具时，保留 HTTP 验收结果，将“浏览器交互检查”标记未执行；不要要求用户补截图，不用静态字符串断言冒充完整 UI 测试。
- [ ] 可选真实 Embedding 验证仅限已经运行的本地服务和已存在模型，不下载、不启动付费服务：同一公开样本集比较 vector/hybrid，保留结果，不自动改生产默认值。不可用则跳过，不阻塞。
- [ ] 完善 3 分钟演示说明和 interview-notes.md：真实技术选择、有限词表取舍、RRF 口径、现有 LoRA 边界、怎样接入真实模型。
- [ ] 检查 git diff --check、产物路径和无关改动，满足验收立即停止。

## 6. Review Focus 与验收条件

重点五类输入，由相关任务覆盖：
1. SQL/NoSQL、TS/其他单词等边界：K1/K2 负例验证，不凭包含关系扩大技能证据。
2. 没有识别要求或没有资料：K2 空数组、null 分母、not_recorded，不冒称用户没有能力。
3. 恶意 HTML、长 JD 和私人内容：K2 输入约束，K3 textContent/原文展示与日志边界。
4. 缺少 Embedding/Chat：K2 demo 仍完整运行；生产路径不静默冒充真实模型成功。
5. 笔记变更及来源一致性：K1 保留原增量测试；K2 所返片段属于实际笔记，演示前后文件哈希不变。

通过条件：
- [ ] K1/K2/K3 指定相关测试通过；所有 skipped/失败有清楚原因。
- [ ] demo 可无 API Key、Ollama、Obsidian 启动并完成三个场景。
- [ ] 现有 /health/search/chat/notes 路径兼容，生产默认仍为 vector。
- [ ] 页面能够呈现来源、关键词证据和缺记录状态；界面验证是否实际执行写清楚。
- [ ] 自动生成三份 Markdown 报告、原始 JSON 和 acceptance.md。
- [ ] 没有新增运行时依赖、真实 Vault 写入、用户 .env 变更或私密样本公开。
- [ ] 文档没有把关键词命中说成能力认证，没有把替身向量结果说成真实模型提升。
- [ ] 用户无需准备或人工标注任何首轮验收数据。

## 7. 执行策略与最终交付

用户已强调时间紧、能自动就自动。对文件名、字段展示和局部样式等可逆选择，agent 自主完成，不逐项征求确认。小的实现差异允许在现有接口边界内解决，并在 acceptance.md 留一句说明；不把小差异升级成新一轮架构讨论。

现有 .venv 可用就复用。不可用时先查项目可用 Python；只安装 pyproject 已声明依赖，不升级整个环境。网络/权限阻止安装时保留已完成工作，明确必要资源；不要重复尝试相同失败方式。未完成必需验证不能写为完成。

只在新付费资源、未授权私人资料、无法安全处理的同文件冲突或不可替代的外部条件上询问用户。模型缺失不属于本首轮的必要外部条件。

最终回复应提供：
1. 完成的 K1–K3、变更清单及未完成项。
2. 本机演示命令和三个可点击报告。
3. 自动测试、浏览器交互、真实模型评测分别是否执行。
4. 两条可用于简历的真实陈述，不编造提升比例或人工标注量。
5. 下轮只推荐一个最有价值的改进点，不自动实施。

本轮完成即结束：交付一个能直接演示的业务流程，避免为了覆盖所有求职方向继续扩建平台。
