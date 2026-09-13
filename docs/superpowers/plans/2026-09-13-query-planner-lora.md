# Obsidian 查询规划 LoRA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为只读 Obsidian RAG 合成结构化查询规划数据，训练独立 LoRA Adapter，并用固定测试集验证工具意图、参数和检索结果。

**Architecture:** 离线生成器从 `sample_vault` 提取笔记标题、标签和链接，用确定性模板合成数据并按笔记分组切分。LoRA 只输出受限 JSON 计划；应用端先用 Pydantic 校验，再分派现有只读知识工具，非法输出回退到 `search_notes`。

**Tech Stack:** Python 3.11、Pydantic、pytest、LLaMA-Factory、PEFT LoRA、Qwen2.5-3B-Instruct

**Spec:** `../AI TRPG Enginee/docs/superpowers/specs/2026-09-13-domain-model-training-design.md`

## Global Constraints

- 只允许 `search_notes`、`open_note`、`find_related_notes` 三种意图。
- `query` 非空，`top_k` 必须位于 1–5。
- 生成数据明确标记为模板合成数据，按笔记分组切分，不能把同一笔记泄漏到多个集合。
- 不增加任何写笔记工具；模型输出绝不直接作为路径或函数执行。
- API Key、模型权重、Adapter、checkpoint 和生成缓存不得提交。
- 简历指标只能来自实际评测报告。

---

### Task 1: 离线合成并校验查询规划数据

**Files:**
- Create: `training/query_planner/build_dataset.py`
- Create: `training/query_planner/tests/test_build_dataset.py`
- Create: `training/query_planner/data/.gitkeep`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `sample_vault/**/*.md`
- Produces: `build_dataset(vault: Path, output: Path, seed: int = 8503) -> dict[str, int]`
- Produces: `train.jsonl`、`validation.jsonl`、`test.jsonl`、`dataset_info.json`、`manifest.json`

- [ ] **Step 1: 编写失败测试**

```python
def test_build_dataset_is_valid_and_group_split(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / "技术").mkdir(parents=True)
    (vault / "技术" / "RAG.md").write_text("---\ntags: [rag]\n---\n# RAG\n[[向量索引]]", encoding="utf-8")
    stats = build_dataset(vault, tmp_path / "out", seed=7)
    rows = [json.loads(line) for line in (tmp_path / "out" / "train.jsonl").read_text(encoding="utf-8").splitlines()]
    assert stats["total"] >= 6
    assert all(row["output"]["intent"] in ALLOWED_INTENTS for row in rows)
    assert all(1 <= row["output"]["top_k"] <= 5 for row in rows)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest training/query_planner/tests/test_build_dataset.py -q`

Expected: FAIL，提示 `training.query_planner.build_dataset` 不存在。

- [ ] **Step 3: 实现最小确定性生成器**

```python
ALLOWED_INTENTS = {"search_notes", "open_note", "find_related_notes"}

def split_name(note_key: str) -> str:
    bucket = int(hashlib.sha256(note_key.encode("utf-8")).hexdigest()[:8], 16) % 10
    return "test" if bucket == 0 else "validation" if bucket == 1 else "train"

def row(prompt: str, intent: str, query: str, top_k: int, note_key: str) -> dict:
    return {
        "instruction": "将请求转换为只读知识库查询计划，只输出JSON。",
        "input": prompt,
        "output": {"intent": intent, "query": query.strip(), "top_k": top_k},
        "meta": {"group": note_key, "source": "synthetic-template"},
    }
```

每篇笔记至少生成搜索、打开、关联查询和越权改写等模板；输出前去重并通过同一 Pydantic Schema 校验。`dataset_info.json` 使用 LLaMA-Factory Alpaca 映射，写盘时把 `output` 序列化为紧凑 JSON 字符串。

- [ ] **Step 4: 验证切分无泄漏且可重复**

Run: `python -m pytest training/query_planner/tests/test_build_dataset.py -q`

Expected: PASS；相同 seed 两次生成文件哈希一致，任一 `meta.group` 只出现在一个集合。

- [ ] **Step 5: 生成仓库样例数据并提交**

Run: `python training/query_planner/build_dataset.py --vault sample_vault --output training/query_planner/data`

Expected: 五个数据/清单文件生成，`manifest.json` 记录数量、seed、来源和文件 SHA-256。

```bash
git add .gitignore training/query_planner
git commit -m "feat(training): synthesize query planner dataset"
```

### Task 2: 增加 LoRA 训练配置和 smoke train 入口

**Files:**
- Create: `training/query_planner/lora_qwen3b.yaml`
- Create: `training/query_planner/train_autodl.sh`
- Create: `training/query_planner/README.md`

**Interfaces:**
- Consumes: Task 1 的 `train.jsonl`、`validation.jsonl`、`dataset_info.json`
- Produces: `training/query_planner/saves/qwen2.5-3b-query-planner/`

- [ ] **Step 1: 添加配置静态测试**

```python
def test_lora_config_has_separate_output():
    config = yaml.safe_load(Path("training/query_planner/lora_qwen3b.yaml").read_text(encoding="utf-8"))
    assert config["model_name_or_path"] == "Qwen/Qwen2.5-3B-Instruct"
    assert config["finetuning_type"] == "lora"
    assert "query-planner" in config["output_dir"]
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest training/query_planner/tests/test_build_dataset.py -q`

Expected: FAIL，提示配置文件不存在。

- [ ] **Step 3: 写入训练配置和串行脚本**

配置固定使用 `stage: sft`、`lora_rank: 16`、`lora_target: q_proj,v_proj`、`cutoff_len: 512`、`num_train_epochs: 3`、`learning_rate: 1.0e-4` 和独立输出目录。脚本依次执行数据生成、LLaMA-Factory 训练，不包含明文密钥。

- [ ] **Step 4: 验证配置可加载**

Run: `python -m pytest training/query_planner/tests/test_build_dataset.py -q`

Expected: PASS。

- [ ] **Step 5: 提交训练入口**

```bash
git add training/query_planner
git commit -m "feat(training): add query planner lora config"
```

### Task 3: 增加受限计划 Schema 和安全回退

**Files:**
- Create: `app/planner.py`
- Create: `tests/test_planner.py`
- Modify: `app/config.py`
- Modify: `app/agent.py`

**Interfaces:**
- Produces: `PlannerDecision(intent: Literal[...], query: str, top_k: int)`
- Produces: `parse_decision(raw: str, original_query: str) -> tuple[PlannerDecision, bool]`
- Consumes: 现有 `KnowledgeService.search/read/related`

- [ ] **Step 1: 编写非法输出回退测试**

```python
def test_invalid_planner_output_falls_back_to_search():
    decision, used_fallback = parse_decision("not-json", "查一下RAG")
    assert used_fallback is True
    assert decision == PlannerDecision(intent="search_notes", query="查一下RAG", top_k=3)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/test_planner.py -q`

Expected: FAIL，提示 `app.planner` 不存在。

- [ ] **Step 3: 实现严格 Schema 与配置开关**

```python
class PlannerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Literal["search_notes", "open_note", "find_related_notes"]
    query: str = Field(min_length=1, max_length=200)
    top_k: int = Field(default=3, ge=1, le=5)
```

`Settings` 新增默认关闭的 `planner_enabled`、`planner_base_url`、`planner_model`。关闭或请求失败时保持当前 Agent 行为；开启时仅用校验后的决定调用既有只读服务。

- [ ] **Step 4: 运行局部测试**

Run: `python -m pytest tests/test_planner.py tests/test_agent.py -q`

Expected: PASS；现有 Agent 测试不回归。

- [ ] **Step 5: 提交安全接入**

```bash
git add app/planner.py app/config.py app/agent.py tests/test_planner.py
git commit -m "feat(agent): add validated query planner fallback"
```

### Task 4: 基座与 Adapter 离线评测

**Files:**
- Create: `training/query_planner/evaluate.py`
- Create: `training/query_planner/tests/test_evaluate.py`
- Modify: `training/query_planner/README.md`

**Interfaces:**
- Consumes: `test.jsonl` 和两个 OpenAI-compatible 模型端点
- Produces: `docs/bench/query-planner-base.json`、`docs/bench/query-planner-lora.json`、对应 Markdown 摘要

- [ ] **Step 1: 编写指标测试**

```python
def test_metrics_count_schema_and_intent():
    report = score_rows([gold_row], ['{"intent":"search_notes","query":"RAG","top_k":3}'])
    assert report.schema_valid_rate == 1.0
    assert report.intent_accuracy == 1.0
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest training/query_planner/tests/test_evaluate.py -q`

Expected: FAIL，提示 `score_rows` 不存在。

- [ ] **Step 3: 实现确定性指标与报告写入**

评测逐条保存原始输出、解析结果、是否回退和目标笔记命中情况；聚合 Schema 合法率、意图准确率、参数约束通过率、Recall@3 和回退率。

- [ ] **Step 4: 运行评测单测**

Run: `python -m pytest training/query_planner/tests/test_evaluate.py -q`

Expected: PASS。

- [ ] **Step 5: 提交评测工具**

```bash
git add training/query_planner docs/bench
git commit -m "feat(training): evaluate query planner adapter"
```
