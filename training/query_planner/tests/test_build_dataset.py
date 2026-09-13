import hashlib
import json
from pathlib import Path

from training.query_planner.build_dataset import build_dataset


ROOT = Path(__file__).resolve().parents[3]


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
    assert all(plan["intent"] in {"search_notes", "open_note", "find_related_notes"} for plan in plans)
    assert all(plan["query"].strip() for plan in plans)
    assert all(1 <= plan["top_k"] <= 5 for plan in plans)
    assert all(row["meta"]["source"] == "synthetic-template" for row in rows)
    assert all(len(row["meta"]["source_note_id"]) == 16 for row in rows)
    assert all(isinstance(row["meta"]["target_note_ids"], list) for row in rows)
    assert all(
        len(note_id) == 16
        for row in rows
        for note_id in row["meta"]["target_note_ids"]
    )
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


def test_build_dataset_normalizes_null_and_scalar_tags(tmp_path: Path):
    """Null tags fall back to the title and scalar tags become one whole tag."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "null.md").write_text("---\ntags:\n---\n# Null tag", encoding="utf-8")
    (vault / "number.md").write_text("---\ntags: 42\n---\n# Number tag", encoding="utf-8")

    output = tmp_path / "out"
    build_dataset(vault, output)
    rows = [row for split_rows in read_rows(output).values() for row in split_rows]
    plans_by_prompt = {
        (row["meta"]["group"], row["input"]): json.loads(row["output"]) for row in rows
    }

    assert plans_by_prompt[("null.md", "查找标签Null tag的笔记")]["query"] == "Null tag"
    assert plans_by_prompt[("number.md", "查找标签42的笔记")]["query"] == "42"


def test_build_dataset_labels_related_note_target(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "RAG.md").write_text("# RAG\n[[Embedding]]", encoding="utf-8")
    (vault / "N1.md").write_text("# Embedding", encoding="utf-8")

    output = tmp_path / "out"
    build_dataset(vault, output)
    rows = [row for split_rows in read_rows(output).values() for row in split_rows]
    related = next(row for row in rows if row["input"] == "找出与RAG关联的笔记")

    assert related["meta"]["target_note_ids"] == [
        hashlib.sha256("N1.md".encode("utf-8")).hexdigest()[:16]
    ]


def test_missing_wikilink_is_not_emitted_as_a_gold_query(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "RAG.md").write_text("# RAG\n[[不存在的笔记]]", encoding="utf-8")

    output = tmp_path / "out"
    build_dataset(vault, output)
    rows = [row for split_rows in read_rows(output).values() for row in split_rows]
    assert not any("不存在的笔记" in row["input"] for row in rows)
    assert all(
        target == hashlib.sha256("RAG.md".encode("utf-8")).hexdigest()[:16]
        for row in rows
        for target in row["meta"]["target_note_ids"]
    )


def test_cross_split_target_rows_are_dropped_without_note_id_leakage(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / "学习").mkdir(parents=True)
    (vault / "技术").mkdir()
    postgres = "学习/PostgreSQL学习记录.md"
    vector = "技术/向量索引迁移.md"
    (vault / postgres).write_text(
        "# PostgreSQL学习记录\n[[向量索引迁移]]",
        encoding="utf-8",
    )
    (vault / vector).write_text("# 向量索引迁移", encoding="utf-8")

    output = tmp_path / "out"
    build_dataset(vault, output)
    rows_by_split = read_rows(output)
    note_splits: dict[str, set[str]] = {}
    for split, rows in rows_by_split.items():
        for row in rows:
            note_ids = [row["meta"]["source_note_id"], *row["meta"]["target_note_ids"]]
            for note_id in note_ids:
                note_splits.setdefault(note_id, set()).add(split)

    assert all(len(splits) == 1 for splits in note_splits.values())
    postgres_id = hashlib.sha256(postgres.encode("utf-8")).hexdigest()[:16]
    vector_id = hashlib.sha256(vector.encode("utf-8")).hexdigest()[:16]
    assert note_splits[postgres_id] != note_splits[vector_id]
    assert not any(
        "向量索引迁移" in row["input"]
        for row in rows_by_split["test"]
    )
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dropped_cross_split_targets"] == 2


def test_sample_vault_keeps_three_nonempty_splits_after_leakage_filter(tmp_path: Path):
    output = tmp_path / "out"
    stats = build_dataset(ROOT / "sample_vault", output)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    rows_by_split = read_rows(output)
    note_splits: dict[str, set[str]] = {}
    for split, rows in rows_by_split.items():
        for row in rows:
            for note_id in [
                row["meta"]["source_note_id"],
                *row["meta"]["target_note_ids"],
            ]:
                note_splits.setdefault(note_id, set()).add(split)

    assert all(stats[split] > 0 for split in ("train", "validation", "test"))
    assert manifest["dropped_cross_split_targets"] > 0
    assert all(len(splits) == 1 for splits in note_splits.values())
