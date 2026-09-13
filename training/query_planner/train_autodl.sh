#!/usr/bin/env bash
# 在单卡云实例上重建数据、校验契约并训练只读查询规划 LoRA。
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
if [[ -n "${PYTHON:-}" ]]; then
  PYTHON_BIN="$PYTHON"
  PYTHON_SOURCE="PYTHON 环境变量"
elif [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
  PYTHON_SOURCE="仓库 .venv/bin/python"
elif [[ -x "$REPO_ROOT/.venv/Scripts/python.exe" ]]; then
  PYTHON_BIN="$REPO_ROOT/.venv/Scripts/python.exe"
  PYTHON_SOURCE="仓库 .venv/Scripts/python.exe"
else
  PYTHON_BIN="python"
  PYTHON_SOURCE="PATH"
fi
LLAMAFACTORY_CLI="${LLAMAFACTORY_CLI:-llamafactory-cli}"
NVIDIA_SMI="${NVIDIA_SMI:-nvidia-smi}"
TEE_COMMAND="${QUERY_PLANNER_TEE_COMMAND:-tee}"
CHECK_ONLY=false

if [[ "${1:-}" == "--check-only" ]]; then
  CHECK_ONLY=true
elif [[ $# -ne 0 ]]; then
  echo "用法：bash train_autodl.sh [--check-only]" >&2
  exit 2
fi

PYTHON_COMMAND="$(command -v "$PYTHON_BIN" 2>/dev/null)" || {
  echo "Python 解释器不可用（$PYTHON_SOURCE）：$PYTHON_BIN；可设置 PYTHON 显式指定。" >&2
  exit 1
}
if [[ ! -x "$PYTHON_COMMAND" ]]; then
  echo "Python 解释器不可执行（$PYTHON_SOURCE）：$PYTHON_COMMAND" >&2
  exit 1
fi
PYTHON_BIN="$PYTHON_COMMAND"

resolve_path() {
  "$PYTHON_BIN" - "$1" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1]).expanduser()
if not path.is_absolute():
    path = Path.cwd() / path
print(path.resolve())
PY
}

CONFIG_PATH="$(resolve_path "${QUERY_PLANNER_CONFIG:-$SCRIPT_DIR/lora_qwen3b.yaml}")"
VAULT_PATH="$(resolve_path "${QUERY_PLANNER_VAULT:-$SCRIPT_DIR/../../sample_vault}")"

for path in "$CONFIG_PATH" "$SCRIPT_DIR/build_dataset.py"; do
  if [[ ! -f "$path" ]]; then
    echo "缺少必需文件：$path" >&2
    exit 1
  fi
done
if [[ ! -d "$VAULT_PATH" ]]; then
  echo "Obsidian Vault 不存在：$VAULT_PATH" >&2
  exit 1
fi

PATHS_OUTPUT="$("$PYTHON_BIN" - "$CONFIG_PATH" <<'PY'
from pathlib import Path
import sys
import yaml

config_path = Path(sys.argv[1]).resolve()
config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
if not isinstance(config, dict):
    raise SystemExit("训练配置必须是 YAML 对象")
required = (
    "model_name_or_path", "stage", "finetuning_type", "dataset", "eval_dataset",
    "dataset_dir", "output_dir",
)
missing = [key for key in required if not config.get(key)]
if missing:
    raise SystemExit(f"训练配置缺少字段：{', '.join(missing)}")

def resolve(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = config_path.parent / path
    return path.resolve()

print(resolve(str(config["dataset_dir"])))
print(resolve(str(config["output_dir"])))
PY
)"
PATHS_OUTPUT="${PATHS_OUTPUT//$'\r'/}"
readarray -t TRAINING_PATHS <<<"$PATHS_OUTPUT"
DATA_DIR="${TRAINING_PATHS[0]}"
OUTPUT_DIR="${TRAINING_PATHS[1]}"

if [[ "$CHECK_ONLY" == false ]]; then
  # 正式运行一旦开始，旧完成标志立即失效；之后即使数据重建失败也不能误报成功。
  "$PYTHON_BIN" - "$OUTPUT_DIR" <<'PY'
from pathlib import Path
import sys

(Path(sys.argv[1]) / ".training-complete").unlink(missing_ok=True)
PY
fi

echo "==> 1/3 按固定 seed 重建模板合成数据"
"$PYTHON_BIN" "$SCRIPT_DIR/build_dataset.py" \
  --vault "$VAULT_PATH" \
  --output "$DATA_DIR" \
  --seed 8503

echo "==> 2/3 校验 LLaMA-Factory 注册和 JSON 输出契约"
DATA_SUMMARY="$("$PYTHON_BIN" - "$CONFIG_PATH" "$DATA_DIR" "$REPO_ROOT" <<'PY'
from pathlib import Path
import sys
import yaml

sys.path.insert(0, str(Path(sys.argv[3]).resolve()))
try:
    from training.query_planner.build_dataset import validate_training_data
except ImportError as exc:
    raise SystemExit(f"缺少 PlannerDecision Schema 依赖：{exc}") from exc

config = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))
data_dir = Path(sys.argv[2])
try:
    counts = validate_training_data(config, data_dir)
except (OSError, ValueError) as exc:
    raise SystemExit(str(exc)) from exc
print(f"train={counts[config['dataset']]} validation={counts[config['eval_dataset']]}")
PY
)"
echo "数据校验通过：$DATA_SUMMARY"

if [[ "$CHECK_ONLY" == true ]]; then
  echo "检查完成；数据为模板合成数据，尚未训练，也未生成 Adapter 或评测报告。"
  exit 0
fi

command -v "$LLAMAFACTORY_CLI" >/dev/null 2>&1 || {
  echo "缺少 LLaMA-Factory：$LLAMAFACTORY_CLI；请先按 README 安装并固定版本。" >&2
  exit 1
}
command -v "$NVIDIA_SMI" >/dev/null 2>&1 || {
  echo "未检测到 NVIDIA GPU 工具：$NVIDIA_SMI" >&2
  exit 1
}
command -v "$TEE_COMMAND" >/dev/null 2>&1 || { echo "缺少 tee，无法保存真实训练日志。" >&2; exit 1; }
"$PYTHON_BIN" - <<'PY'
try:
    from peft import PeftConfig  # noqa: F401
    from safetensors import safe_open  # noqa: F401
except ImportError as exc:
    raise SystemExit(f"缺少 Adapter 验证依赖：{exc.name}；请先安装与训练环境匹配的 peft 和 safetensors") from exc
PY
GPU_INFO="$("$NVIDIA_SMI" --query-gpu=name,memory.total,driver_version --format=csv,noheader)"
if [[ -z "$GPU_INFO" ]]; then
  echo "未检测到可用 NVIDIA GPU。" >&2
  exit 1
fi

LOG_DIR="$(resolve_path "${QUERY_PLANNER_LOG_DIR:-$SCRIPT_DIR/logs}")"
"$PYTHON_BIN" - "$LOG_DIR" <<'PY'
from pathlib import Path
import os
import sys
import tempfile

directory = Path(sys.argv[1])
directory.mkdir(parents=True, exist_ok=True)
fd, probe = tempfile.mkstemp(prefix=".write-check-", dir=directory)
os.close(fd)
Path(probe).unlink()
PY

RUN_ID="${QUERY_PLANNER_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
LOG_FILE="$LOG_DIR/train-$RUN_ID.log"
BACKUP_DIR="${OUTPUT_DIR}.backup-${RUN_ID}"
BACKUP_RESULT="$("$PYTHON_BIN" - "$OUTPUT_DIR" "$BACKUP_DIR" "$CONFIG_PATH" "$DATA_DIR" <<'PY'
from pathlib import Path
import shutil
import sys

output, backup, config_path, data_dir = map(lambda value: Path(value).resolve(), sys.argv[1:])
unsafe = {Path(output.anchor), Path.home().resolve(), config_path.parent, data_dir}
if output in unsafe:
    raise SystemExit(f"拒绝移动不安全的 Adapter 输出目录：{output}")
if not output.exists():
    print("none")
elif not output.is_dir():
    raise SystemExit(f"Adapter 输出路径不是目录：{output}")
elif backup.exists():
    raise SystemExit(f"备份目录已存在，请更换 QUERY_PLANNER_RUN_ID：{backup}")
else:
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(output), str(backup))
    print(backup)
PY
)"
if [[ "$BACKUP_RESULT" != "none" ]]; then
  echo "旧 Adapter 已移至可恢复备份：$BACKUP_RESULT"
fi
echo "==> 3/3 训练查询规划 Adapter"
echo "GPU：$GPU_INFO"
set +e
(cd "$(dirname "$CONFIG_PATH")" && "$LLAMAFACTORY_CLI" train "$CONFIG_PATH") 2>&1 | "$TEE_COMMAND" "$LOG_FILE"
PIPELINE_STATUS=("${PIPESTATUS[@]}")
TRAIN_STATUS="${PIPELINE_STATUS[0]}"
TEE_STATUS="${PIPELINE_STATUS[1]}"
set -e
if [[ "$TRAIN_STATUS" -ne 0 ]]; then
  echo "训练失败；检查真实日志：$LOG_FILE" >&2
  exit "$TRAIN_STATUS"
fi
if [[ "$TEE_STATUS" -ne 0 ]]; then
  echo "训练输出未能可靠写入日志：$LOG_FILE" >&2
  exit "$TEE_STATUS"
fi

"$PYTHON_BIN" - "$OUTPUT_DIR" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import sys

from peft import PeftConfig
from safetensors import safe_open

output = Path(sys.argv[1])
config_path = output / "adapter_config.json"
weights_path = output / "adapter_model.safetensors"
if not config_path.is_file() or not weights_path.is_file() or weights_path.stat().st_size == 0:
    raise SystemExit(f"训练命令结束，但 Adapter 产物不完整：{output}")
try:
    try:
        PeftConfig.from_pretrained(str(output), local_files_only=True)
    except TypeError:
        PeftConfig.from_pretrained(str(output))
    with safe_open(str(weights_path), framework="pt", device="cpu") as weights:
        if not list(weights.keys()):
            raise ValueError("权重文件不包含任何张量")
except Exception as exc:
    raise SystemExit(f"Adapter 产物无法解析：{exc}") from exc
(output / ".training-complete").write_text(datetime.now(timezone.utc).isoformat() + "\n", encoding="utf-8")
PY

echo "训练完成。Adapter：$OUTPUT_DIR"
echo "真实训练日志：$LOG_FILE"
echo "尚未生成评测报告；下一步必须用固定测试集实测 base 与 Adapter。"
