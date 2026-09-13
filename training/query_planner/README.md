# Obsidian 查询规划 LoRA

这个目录训练的是一个独立的“查询规划器”，不是知识问答模型。它只把用户请求转换为受限 JSON：

```json
{"intent":"search_notes","query":"LangChain 工具调用","top_k":3}
```

允许的意图只有 `search_notes`、`open_note` 和 `find_related_notes`。模型不直接执行工具、不拼接文件路径，也不会创建、修改、移动或删除 Obsidian 笔记；运行时仍须先做 Schema 校验，再调用现有只读知识服务。非法输出必须回退到普通检索。

## 数据来源与边界

`build_dataset.py` 从 `sample_vault` 的标题、标签和链接离线生成模板合成数据，以笔记为组切分，固定 seed 为 `8503`。写入 LLaMA-Factory 的 `output` 是 JSON 字符串，注册名与 `data/dataset_info.json` 一致。个人真实 Vault、缓存、模型权重、Adapter、checkpoint 和日志均不提交仓库。

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

脚本不会自动安装依赖，也不读取或保存 API Key。正式训练前会检查配置、数据、`llamafactory-cli`、GPU 和日志目录写权限；新运行会先让旧的 `.training-complete` 标志失效。只有训练命令成功且检测到真实 Adapter 文件后才重新写入完成标志。

默认 Adapter 输出目录为 `training/query_planner/saves/qwen2.5-3b-query-planner/`，日志位于 `training/query_planner/logs/`。这些产物用于后续离线评测，不应提交 Git。
