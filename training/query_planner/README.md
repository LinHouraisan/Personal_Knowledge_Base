# Obsidian 查询规划 LoRA

这个目录训练的是一个独立的“查询规划器”，不是知识问答模型。它只把用户请求转换为受限 JSON：

```json
{"intent":"search_notes","query":"LangChain 工具调用","top_k":3}
```

允许的意图只有 `search_notes`、`open_note` 和 `find_related_notes`。模型不直接执行工具、不拼接文件路径，也不会创建、修改、移动或删除 Obsidian 笔记；运行时仍须先做 Schema 校验，再调用现有只读知识服务。非法输出必须回退到普通检索。

## 数据来源与边界

`build_dataset.py` 从 `sample_vault` 的标题、标签和链接离线生成模板合成数据，固定 seed 为 `8503`。先按 source 笔记稳定切分；若一条样本的显式 target 笔记属于另一 split，整条样本会被丢弃，不会仅清空 target 后保留泄漏 query。`manifest.json` 用 `dropped_cross_split_targets` 记录这一数据损失。失效 wikilink 不会被当成 gold query 或 target，相应检索模板回到已存在的 source 标题。因此一个真实 note ID 无论作为 source 还是 target 都只出现在一个 split。写入 LLaMA-Factory 的 `output` 是 JSON 字符串，注册名与 `data/dataset_info.json` 一致。个人真实 Vault、缓存、模型权重、Adapter、checkpoint 和日志均不提交仓库。

当前仓库只提供可复现的数据、配置和训练入口，**尚未完成真实 LoRA 训练，也没有可用于简历的提升数字**。指标只能来自后续固定测试集生成的 base/Adapter 真实评测报告。

## 本地轻量检查

先激活包含项目依赖的 Python 环境，然后运行：

```bash
bash training/query_planner/train_autodl.sh --check-only
```

该命令会重新生成并校验训练/验证数据，但不会检查 GPU、启动训练、创建 Adapter 或伪造训练日志。可以用相对路径或 `~` 指定配置与 Vault：

```bash
QUERY_PLANNER_CONFIG=training/query_planner/lora_qwen3b.yaml \
QUERY_PLANNER_VAULT=~/my-sanitized-vault \
bash training/query_planner/train_autodl.sh --check-only
```

仅使用可公开或脱敏的 Vault。若从其他目录运行，相对路径按当前工作目录解析；配置内的 `dataset_dir` 和 `output_dir` 按配置文件所在目录解析。

## AutoDL 单卡训练

推荐一张约 24GB 显存的 NVIDIA GPU。提前安装并固定 LLaMA-Factory 版本、准备 Qwen 基座访问权限，然后在已激活环境中执行：

```bash
llamafactory-cli --help
nvidia-smi
bash training/query_planner/train_autodl.sh
```

脚本不会自动安装依赖，也不读取或保存 API Key。正式训练前会检查配置、数据、`llamafactory-cli`、GPU、`peft`、`safetensors` 和日志目录写权限；新运行在数据重建前就会让旧的 `.training-complete` 标志失效。全部预检通过后，已有 Adapter 目录会按本次 run id 移到同级 `.backup-<run-id>` 目录，再从干净输出目录开始训练，旧产物不会被删除。

本入口有意只接受 LLaMA-Factory 默认生成的 `adapter_model.safetensors`，不接受旧式 `adapter_model.bin`。训练命令成功后仍会用 PEFT 解析配置，并用 safetensors 打开非空权重；两项均通过才重新写入完成标志。

默认 Adapter 输出目录为 `training/query_planner/saves/qwen2.5-3b-query-planner/`，日志位于 `training/query_planner/logs/`。这些产物用于后续离线评测，不应提交 Git。

## 基座与 Adapter 离线评测

`evaluate.py` 每次只调用一个 OpenAI-compatible Chat Completions 端点，然后将通过 Schema 校验的计划（或安全回退计划）交给现有 `KnowledgeService` 只读分派。因此 Recall@3 来自实际分派返回的笔记 ID，不是把 gold 计划当成检索命中。

先重新生成带 `target_note_ids` 的固定数据，并确保示例 Vault 已用同一 Embedding 配置建好索引：

```bash
python training/query_planner/build_dataset.py \
  --vault sample_vault \
  --output training/query_planner/data
```

评测程序会对读入的 `test.jsonl` 字节计算 SHA-256，并与 `manifest.json` 中的同一文件哈希和样本数核对。空数据、哈希不符、样本数不符或端点输出失败时不发布报告。JSON 和 Markdown 报告以可回滚的成对方式发布，避免只留下半套文件。

先单独跑基座模型：

```bash
export PLANNER_API_KEY='...'
python -m training.query_planner.evaluate \
  --base-url http://127.0.0.1:8001/v1 \
  --model Qwen/Qwen2.5-3B-Instruct \
  --vault sample_vault \
  --index data/index.json \
  --embedding-base-url http://127.0.0.1:11434/v1 \
  --embedding-model bge-m3 \
  --output-prefix docs/bench/query-planner-base
```

再单独启动加载 Adapter 的端点，使用它对外公开的模型名运行：

```bash
python -m training.query_planner.evaluate \
  --base-url http://127.0.0.1:8002/v1 \
  --model qwen2.5-3b-query-planner \
  --vault sample_vault \
  --index data/index.json \
  --embedding-base-url http://127.0.0.1:11434/v1 \
  --embedding-model bge-m3 \
  --output-prefix docs/bench/query-planner-lora
```

Windows PowerShell 用 `$env:PLANNER_API_KEY='...'` 设置环境变量。程序只记录公开模型名、数据哈希、manifest seed/样本数、逐条原始输出、解析/回退结果、检索 ID 和延迟；不记录 API Key 或请求头。

指标口径固定如下：

- Schema 合法率只表示原始 JSON 能否被目标 `PlannerDecision` Pydantic Schema 严格解析（含 extra、query 长度和 `top_k` 类型/范围）。路径安全是 Schema 之后的运行时检查；因此 Schema 可以合法但仍因不安全 query 而回退。
- 意图准确率独立比较原始 JSON 对象的 `intent` 与 gold intent；即使 `top_k` 越界或存在 extra 字段，意图仍可单独计对。
- 参数约束通过率只检查原始 `query` 经 trim 后长度为 1–200，以及 `top_k` 是严格整数且位于 1–5；`extra` 字段不影响该指标，也不因回退值变好。
- 回退率只使用运行时 `parse_decision` 返回的 `used_fallback`。
- Recall@3 看最终只读分派的前三个去重笔记 ID；只有显式且经 Vault 校验存在的 `target_note_ids` 才进入分母。旧行缺少该字段或空列表时不从 `meta.group` 推断命中，报告会另记分母样本数。
- 空集的所有比率定义为 `0.0`，但 CLI 对空测试集直接拒绝发布。

**目前仓库中没有实际跑出的 base 或 Adapter 报告。** 只能比较 `data_sha256`、manifest seed 和样本数完全一致的两份报告；不得直接比较不同测试集的数字，也不得把未运行状态写成已完成的训练收益。
