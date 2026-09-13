import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

import pytest
import yaml


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


def test_lora_config_matches_query_planner_dataset_contract():
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

    info = json.loads((TRAINING_DIR / config["dataset_dir"] / "dataset_info.json").read_text(encoding="utf-8"))
    assert info[config["dataset"]]["file_name"] == "train.jsonl"
    assert info[config["eval_dataset"]]["file_name"] == "validation.jsonl"
    train_row = json.loads((TRAINING_DIR / "data" / "train.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert isinstance(train_row["output"], str)
    assert set(json.loads(train_row["output"])) == {"intent", "query", "top_k"}


@pytest.mark.parametrize("config_ref", ["config.yaml", "~/config.yaml"])
def test_check_only_rebuilds_and_validates_data_with_portable_paths(tmp_path: Path, config_ref: str):
    """Breaking relative/tilde path resolution or dataset validation must fail."""
    home = tmp_path / "home"
    home.mkdir()
    vault = home / "vault"
    vault.mkdir()
    (vault / "RAG.md").write_text("# RAG\n[[向量索引]]\n", encoding="utf-8")
    (vault / "N4.md").write_text("# 验证集笔记\n", encoding="utf-8")
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


def test_formal_run_invalidates_stale_completion_before_gpu_check(tmp_path: Path):
    """A prior completion marker must never survive the start of a new failed run."""
    home = tmp_path / "home"
    home.mkdir()
    vault = home / "vault"
    vault.mkdir()
    (vault / "RAG.md").write_text("# RAG\n", encoding="utf-8")
    (vault / "N4.md").write_text("# 验证集笔记\n", encoding="utf-8")
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


def test_formal_run_marks_complete_only_after_real_adapter_files(tmp_path: Path):
    """Losing a pipeline exit status or accepting absent Adapter files must fail."""
    home = tmp_path / "home"
    home.mkdir()
    vault = home / "vault"
    vault.mkdir()
    (vault / "RAG.md").write_text("# RAG\n", encoding="utf-8")
    (vault / "N4.md").write_text("# 验证集笔记\n", encoding="utf-8")
    config = home / "config.yaml"
    _write_config(config)
    output = home / "saves" / "query-planner"

    fake_cli = home / "llamafactory-cli"
    fake_cli.write_text(
        "#!/usr/bin/env bash\n"
        "set -e\n"
        "mkdir -p \"$TEST_OUTPUT_DIR\"\n"
        "printf '{}\\n' > \"$TEST_OUTPUT_DIR/adapter_config.json\"\n"
        "printf 'adapter\\n' > \"$TEST_OUTPUT_DIR/adapter_model.safetensors\"\n"
        "echo 'mock train complete'\n",
        encoding="utf-8",
        newline="\n",
    )
    fake_cli.chmod(0o755)
    fake_gpu = home / "nvidia-smi"
    fake_gpu.write_text("#!/usr/bin/env bash\necho 'Mock GPU, 24576 MiB, 1.0'\n", encoding="utf-8", newline="\n")
    fake_gpu.chmod(0o755)

    result = subprocess.run(
        [_bash(), SCRIPT.as_posix()],
        cwd=home,
        env={
            **os.environ,
            "HOME": str(home),
            "USERPROFILE": str(home),
            "QUERY_PLANNER_CONFIG": "config.yaml",
            "QUERY_PLANNER_VAULT": "vault",
            "QUERY_PLANNER_LOG_DIR": "logs",
            "QUERY_PLANNER_RUN_ID": "success-test",
            "LLAMAFACTORY_CLI": fake_cli.as_posix(),
            "NVIDIA_SMI": fake_gpu.as_posix(),
            "PYTHON": Path(sys.executable).as_posix(),
            "TEST_OUTPUT_DIR": output.as_posix(),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (output / ".training-complete").is_file()
    assert "mock train complete" in (home / "logs" / "train-success-test.log").read_text(encoding="utf-8")
