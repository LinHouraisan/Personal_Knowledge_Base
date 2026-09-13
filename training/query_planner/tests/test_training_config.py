import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

import pytest
import yaml

from training.query_planner.build_dataset import build_dataset, validate_training_data


ROOT = Path(__file__).resolve().parents[3]
TRAINING_DIR = ROOT / "training" / "query_planner"
CONFIG = TRAINING_DIR / "lora_qwen3b.yaml"
SCRIPT = TRAINING_DIR / "train_autodl.sh"


def _bash() -> str:
    bash = shutil.which("bash")
    if not bash and os.name == "nt":
        git_bash = Path("C:/Program Files/Git/bin/bash.exe")
        bash = str(git_bash) if git_bash.is_file() else None
    if not bash:
        pytest.skip("当前环境没有 Bash")
    return bash


def _write_config(path: Path, *, output_dir: str = "saves/query-planner") -> None:
    path.write_text(
        textwrap.dedent(
            f"""
            model_name_or_path: Qwen/Qwen2.5-3B-Instruct
            stage: sft
            do_train: true
            do_eval: true
            finetuning_type: lora
            lora_rank: 16
            lora_target: q_proj,v_proj
            dataset: query_planner_train
            eval_dataset: query_planner_validation
            dataset_dir: data
            template: qwen
            cutoff_len: 512
            learning_rate: 1.0e-4
            num_train_epochs: 3.0
            output_dir: {output_dir}
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def _write_vault(vault: Path) -> None:
    vault.mkdir()
    (vault / "RAG.md").write_text("# RAG\n[[向量索引]]\n", encoding="utf-8")
    (vault / "N4.md").write_text("# 验证集笔记\n", encoding="utf-8")


def _write_training_contract(data_dir: Path, plan: dict) -> dict:
    data_dir.mkdir()
    row = {
        "instruction": "只输出 JSON",
        "input": "查找 RAG",
        "output": json.dumps(plan, ensure_ascii=False),
    }
    line = json.dumps(row, ensure_ascii=False) + "\n"
    for name in ("train.jsonl", "validation.jsonl"):
        (data_dir / name).write_text(line, encoding="utf-8")
    (data_dir / "dataset_info.json").write_text(
        json.dumps(
            {
                "query_planner_train": {
                    "file_name": "train.jsonl",
                    "formatting": "alpaca",
                    "columns": {"prompt": "instruction", "query": "input", "response": "output"},
                },
                "query_planner_validation": {
                    "file_name": "validation.jsonl",
                    "formatting": "alpaca",
                    "columns": {"prompt": "instruction", "query": "input", "response": "output"},
                },
            }
        ),
        encoding="utf-8",
    )
    (data_dir / "manifest.json").write_text(
        json.dumps({"source": "synthetic-template"}), encoding="utf-8"
    )
    return {
        "dataset": "query_planner_train",
        "eval_dataset": "query_planner_validation",
    }


def _write_fake_runtime(home: Path, *, cli_source: str) -> tuple[Path, Path, Path]:
    fake_cli = home / "llamafactory-cli"
    fake_cli.write_text(cli_source, encoding="utf-8", newline="\n")
    fake_cli.chmod(0o755)
    fake_gpu = home / "nvidia-smi"
    fake_gpu.write_text("#!/usr/bin/env bash\necho 'Mock GPU, 24576 MiB, 1.0'\n", encoding="utf-8", newline="\n")
    fake_gpu.chmod(0o755)

    modules = home / "fake_modules"
    peft = modules / "peft"
    peft.mkdir(parents=True)
    (peft / "__init__.py").write_text(
        "import json\n"
        "from pathlib import Path\n"
        "class PeftConfig:\n"
        "    @classmethod\n"
        "    def from_pretrained(cls, path, local_files_only=True):\n"
        "        json.loads((Path(path) / 'adapter_config.json').read_text(encoding='utf-8'))\n"
        "        return cls()\n",
        encoding="utf-8",
    )
    safetensors = modules / "safetensors"
    safetensors.mkdir()
    (safetensors / "__init__.py").write_text(
        "from pathlib import Path\n"
        "class _Reader:\n"
        "    def __init__(self, path):\n"
        "        if Path(path).read_bytes() != b'valid-safetensors':\n"
        "            raise ValueError('invalid safetensors')\n"
        "    def __enter__(self): return self\n"
        "    def __exit__(self, *args): return False\n"
        "    def keys(self): return ['lora.weight']\n"
        "def safe_open(path, framework='pt', device='cpu'):\n"
        "    return _Reader(path)\n",
        encoding="utf-8",
    )
    return fake_cli, fake_gpu, modules


def _formal_env(home: Path, fake_cli: Path, fake_gpu: Path, modules: Path) -> dict[str, str]:
    return {
        **os.environ,
        "HOME": str(home),
        "USERPROFILE": str(home),
        "QUERY_PLANNER_CONFIG": "config.yaml",
        "QUERY_PLANNER_VAULT": "vault",
        "QUERY_PLANNER_LOG_DIR": "logs",
        "QUERY_PLANNER_RUN_ID": "test-run",
        "LLAMAFACTORY_CLI": fake_cli.as_posix(),
        "NVIDIA_SMI": fake_gpu.as_posix(),
        "PYTHON": Path(sys.executable).as_posix(),
        "PYTHONPATH": str(modules) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }


def test_lora_config_matches_query_planner_dataset_contract(tmp_path: Path):
    """A wrong base, LoRA target, split registration, or output directory must fail."""
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))

    assert config["model_name_or_path"] == "Qwen/Qwen2.5-3B-Instruct"
    assert config["stage"] == "sft"
    assert config["finetuning_type"] == "lora"
    assert config["lora_rank"] == 16
    assert config["lora_target"] == "q_proj,v_proj"
    assert config["cutoff_len"] == 512
    assert config["num_train_epochs"] == 3.0
    assert config["learning_rate"] == 1.0e-4
    assert config["dataset"] == "query_planner_train"
    assert config["eval_dataset"] == "query_planner_validation"
    assert "query-planner" in config["output_dir"]

    vault = tmp_path / "vault"
    _write_vault(vault)
    data_dir = tmp_path / "data"
    build_dataset(vault, data_dir)
    info = json.loads((data_dir / "dataset_info.json").read_text(encoding="utf-8"))
    assert info[config["dataset"]]["file_name"] == "train.jsonl"
    assert info[config["eval_dataset"]]["file_name"] == "validation.jsonl"
    train_row = json.loads((data_dir / "train.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert isinstance(train_row["output"], str)
    assert set(json.loads(train_row["output"])) == {"intent", "query", "top_k"}


@pytest.mark.parametrize(
    "plan",
    [
        {"intent": "search_notes", "query": "长" * 201, "top_k": 3},
        {"intent": "search_notes", "query": "RAG", "top_k": 3, "extra": True},
        {"intent": "search_notes", "query": "RAG", "top_k": True},
    ],
    ids=["query-too-long", "extra-field", "bool-top-k"],
)
def test_training_preflight_rejects_gold_outside_runtime_schema(tmp_path: Path, plan: dict):
    """Weakening the preflight below PlannerDecision's contract must fail."""
    data_dir = tmp_path / "data"
    config = _write_training_contract(data_dir, plan)

    with pytest.raises(ValueError, match="PlannerDecision"):
        validate_training_data(config, data_dir)


@pytest.mark.parametrize("config_ref", ["config.yaml", "~/config.yaml"])
def test_check_only_rebuilds_and_validates_data_with_portable_paths(tmp_path: Path, config_ref: str):
    """Breaking relative/tilde path resolution or dataset validation must fail."""
    home = tmp_path / "home"
    home.mkdir()
    vault = home / "vault"
    _write_vault(vault)
    config = home / "config.yaml"
    _write_config(config)

    result = subprocess.run(
        [_bash(), SCRIPT.as_posix(), "--check-only"],
        cwd=home,
        env={
            **os.environ,
            "HOME": str(home),
            "USERPROFILE": str(home),
            "QUERY_PLANNER_CONFIG": config_ref,
            "QUERY_PLANNER_VAULT": "~/vault",
            "PYTHON": Path(sys.executable).as_posix(),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "train=" in result.stdout
    assert "尚未训练" in result.stdout
    assert (home / "data" / "manifest.json").is_file()
    assert not (home / "saves" / "query-planner").exists()


def test_check_only_prefers_repository_venv_over_broken_path_python(tmp_path: Path):
    """Removing PYTHON must not let a broken PATH interpreter shadow the repo venv."""
    repo_python = next(
        (
            candidate
            for candidate in (ROOT / ".venv" / "bin" / "python", ROOT / ".venv" / "Scripts" / "python.exe")
            if candidate.is_file()
        ),
        None,
    )
    if repo_python is None:
        pytest.skip("仓库没有可用于验证自动选择的 .venv Python")

    home = tmp_path / "home"
    home.mkdir()
    _write_vault(home / "vault")
    _write_config(home / "config.yaml")
    bad_bin = tmp_path / "bad-bin"
    bad_bin.mkdir()
    marker = tmp_path / "bad-python-used"
    bad_python = bad_bin / "python"
    bad_python.write_text(
        "#!/usr/bin/env bash\nprintf 'used' > \"$BAD_PYTHON_MARKER\"\nexit 91\n",
        encoding="utf-8",
        newline="\n",
    )
    bad_python.chmod(0o755)
    env = {**os.environ}
    env.pop("PYTHON", None)
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "QUERY_PLANNER_CONFIG": "config.yaml",
            "QUERY_PLANNER_VAULT": "vault",
            "BAD_PYTHON_MARKER": marker.as_posix(),
            "PATH": str(bad_bin) + os.pathsep + env.get("PATH", ""),
        }
    )

    result = subprocess.run(
        [_bash(), SCRIPT.as_posix(), "--check-only"],
        cwd=home,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "数据校验通过" in result.stdout
    assert not marker.exists()


def test_formal_run_invalidates_stale_completion_before_gpu_check(tmp_path: Path):
    """A prior completion marker must never survive the start of a new failed run."""
    home = tmp_path / "home"
    home.mkdir()
    vault = home / "vault"
    _write_vault(vault)
    config = home / "config.yaml"
    _write_config(config)
    marker = home / "saves" / "query-planner" / ".training-complete"
    marker.parent.mkdir(parents=True)
    marker.write_text("stale\n", encoding="utf-8")

    fake_cli = home / "llamafactory-cli"
    fake_cli.write_text("#!/usr/bin/env bash\nexit 99\n", encoding="utf-8", newline="\n")
    fake_cli.chmod(0o755)

    result = subprocess.run(
        [_bash(), SCRIPT.as_posix()],
        cwd=home,
        env={
            **os.environ,
            "HOME": str(home),
            "USERPROFILE": str(home),
            "QUERY_PLANNER_CONFIG": "config.yaml",
            "QUERY_PLANNER_VAULT": "vault",
            "LLAMAFACTORY_CLI": fake_cli.as_posix(),
            "NVIDIA_SMI": "missing-nvidia-smi-for-test",
            "PYTHON": Path(sys.executable).as_posix(),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "NVIDIA GPU" in result.stderr
    assert not marker.exists()


def test_formal_run_invalidates_marker_before_dataset_build(tmp_path: Path):
    """A data-build failure must not leave an earlier successful-run marker valid."""
    home = tmp_path / "home"
    home.mkdir()
    vault = home / "vault"
    vault.mkdir()
    (vault / "broken.md").write_text("---\ntags: [\n---\n# Broken\n", encoding="utf-8")
    config = home / "config.yaml"
    _write_config(config)
    marker = home / "saves" / "query-planner" / ".training-complete"
    marker.parent.mkdir(parents=True)
    marker.write_text("stale\n", encoding="utf-8")

    result = subprocess.run(
        [_bash(), SCRIPT.as_posix()],
        cwd=home,
        env={
            **os.environ,
            "HOME": str(home),
            "USERPROFILE": str(home),
            "QUERY_PLANNER_CONFIG": "config.yaml",
            "QUERY_PLANNER_VAULT": "vault",
            "PYTHON": Path(sys.executable).as_posix(),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert not marker.exists()


def test_noop_training_cannot_reuse_old_adapter_and_backup_is_preserved(tmp_path: Path):
    """A successful no-op CLI must not let stale Adapter files pass this run."""
    home = tmp_path / "home"
    home.mkdir()
    vault = home / "vault"
    _write_vault(vault)
    config = home / "config.yaml"
    _write_config(config)
    output = home / "saves" / "query-planner"
    output.mkdir(parents=True)
    (output / "adapter_config.json").write_text("{}\n", encoding="utf-8")
    (output / "adapter_model.safetensors").write_bytes(b"valid-safetensors")
    (output / ".training-complete").write_text("stale\n", encoding="utf-8")
    fake_cli, fake_gpu, modules = _write_fake_runtime(home, cli_source="#!/usr/bin/env bash\nexit 0\n")

    result = subprocess.run(
        [_bash(), SCRIPT.as_posix()],
        cwd=home,
        env=_formal_env(home, fake_cli, fake_gpu, modules),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    backups = list((home / "saves").glob("query-planner.backup-test-run*"))
    assert result.returncode != 0
    assert "Adapter 产物不完整" in result.stderr
    assert not (output / ".training-complete").exists()
    assert len(backups) == 1
    assert (backups[0] / "adapter_config.json").is_file()
    assert (backups[0] / "adapter_model.safetensors").read_bytes() == b"valid-safetensors"


def test_formal_run_marks_complete_only_after_valid_adapter_files(tmp_path: Path):
    """Losing a pipeline exit status or accepting absent Adapter files must fail."""
    home = tmp_path / "home"
    home.mkdir()
    vault = home / "vault"
    _write_vault(vault)
    config = home / "config.yaml"
    _write_config(config)
    output = home / "saves" / "query-planner"

    fake_cli, fake_gpu, modules = _write_fake_runtime(
        home,
        cli_source=(
            "#!/usr/bin/env bash\n"
            "set -e\n"
            "mkdir -p \"$TEST_OUTPUT_DIR\"\n"
            "printf '{}\\n' > \"$TEST_OUTPUT_DIR/adapter_config.json\"\n"
            "printf 'valid-safetensors' > \"$TEST_OUTPUT_DIR/adapter_model.safetensors\"\n"
            "echo 'mock train complete'\n"
        ),
    )

    env = _formal_env(home, fake_cli, fake_gpu, modules)
    env["QUERY_PLANNER_RUN_ID"] = "success-test"
    env["TEST_OUTPUT_DIR"] = output.as_posix()

    result = subprocess.run(
        [_bash(), SCRIPT.as_posix()],
        cwd=home,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (output / ".training-complete").is_file()
    assert "mock train complete" in (home / "logs" / "train-success-test.log").read_text(encoding="utf-8")
