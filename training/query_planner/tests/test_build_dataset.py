import hashlib
import json
from pathlib import Path

from training.query_planner.build_dataset import ALLOWED_INTENTS, build_dataset


def read_rows(output: Path) -> dict[str, list[dict]]:
    return {
        split: [json.loads(line) for line in (output / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()]
        for split in ("train", "validation", "test")
    }


def test_build_dataset_is_valid_and_group_split(tmp_path: Path):
    """A missing template, unsafe plan, or cross-split note group must fail."""
    vault = tmp_path / "vault"
    (vault / "技术").mkdir(parents=True)
    (vault / "技术" / "RAG.md").write_text(
        "---\ntags: [rag]\n---\n# RAG\n[[向量索引]]", encoding="utf-8"
    )

    output = tmp_path / "out"
    stats = build_dataset(vault, output, seed=7)
    rows_by_split = read_rows(output)
    rows = [row for split_rows in rows_by_split.values() for row in split_rows]
    plans = [json.loads(row["output"]) for row in rows]

    assert stats["total"] >= 6
    assert all(plan["intent"] in ALLOWED_INTENTS for plan in plans)
    assert all(1 <= plan["top_k"] <= 5 for plan in plans)
    assert all(row["meta"]["source"] == "synthetic-template" for row in rows)
    assert {row["meta"]["group"] for row in rows} == {"技术/RAG.md"}
    assert sum(bool(split_rows) for split_rows in rows_by_split.values()) == 1


def test_build_dataset_is_reproducible_and_declares_alpaca_mapping(tmp_path: Path):
    """Changing output paths must not change a seeded dataset or its training mapping."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "RAG.md").write_text("# RAG", encoding="utf-8")

    first = tmp_path / "first"
    second = tmp_path / "second"
    build_dataset(vault, first, seed=8503)
    build_dataset(vault, second, seed=8503)

    names = ("train.jsonl", "validation.jsonl", "test.jsonl", "dataset_info.json", "manifest.json")
    assert {
        name: hashlib.sha256((first / name).read_bytes()).hexdigest() for name in names
    } == {
        name: hashlib.sha256((second / name).read_bytes()).hexdigest() for name in names
    }

    info = json.loads((first / "dataset_info.json").read_text(encoding="utf-8"))
    assert info["query_planner_train"]["formatting"] == "alpaca"
    assert info["query_planner_train"]["columns"] == {
        "prompt": "instruction",
        "query": "input",
        "response": "output",
    }
