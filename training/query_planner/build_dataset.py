"""Build deterministic, template-synthetic data for read-only query planning."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.planner import PlannerDecision
from app.vault import scan_vault


ALLOWED_INTENTS = {"search_notes", "open_note", "find_related_notes"}
SPLITS = ("train", "validation", "test")
INSTRUCTION = "将请求转换为只读知识库查询计划，只输出JSON。"


def split_name(note_key: str) -> str:
    bucket = int(hashlib.sha256(note_key.encode("utf-8")).hexdigest()[:8], 16) % 10
    return "test" if bucket == 0 else "validation" if bucket == 1 else "train"


def _note_id(note_key: str) -> str:
    return hashlib.sha256(note_key.encode("utf-8")).hexdigest()[:16]


def row(
    prompt: str,
    intent: str,
    query: str,
    top_k: int,
    note_key: str,
    target_note_ids: list[str],
) -> dict:
    plan = PlannerDecision.model_validate(
        {"intent": intent, "query": query, "top_k": top_k}
    )
    return {
        "instruction": INSTRUCTION,
        "input": prompt,
        "output": plan.model_dump(),
        "meta": {
            "group": note_key,
            "source": "synthetic-template",
            "source_note_id": _note_id(note_key),
            "target_note_ids": target_note_ids,
        },
    }


def _template_rows(
    note_key: str,
    title: str,
    tag: str,
    link: str,
    related_note_keys: list[str],
    link_target_key: str | None,
) -> list[dict]:
    own_target = [_note_id(note_key)]
    related_targets = [_note_id(target) for target in related_note_keys]
    link_target = [_note_id(link_target_key)] if link_target_key else []
    semantic_title = title.strip()[:200]
    semantic_tag = tag.strip()[:200]
    semantic_link = link.strip()[:200]
    rows = [
        row(
            f"搜索与{title}相关的笔记",
            "search_notes",
            semantic_title,
            3,
            note_key,
            own_target,
        ),
        row(
            f"查找标签{tag}的笔记",
            "search_notes",
            semantic_tag,
            3,
            note_key,
            own_target,
        ),
        row(
            f"修改{title}并写入知识库",
            "search_notes",
            semantic_title,
            3,
            note_key,
            own_target,
        ),
        row(
            f"检索{link}的相关资料",
            "search_notes",
            semantic_link,
            3,
            note_key,
            link_target or own_target,
        ),
    ]
    if len(note_key.strip()) <= 200:
        rows.extend(
            [
                row(f"打开{title}", "open_note", note_key, 1, note_key, own_target),
                row(
                    f"找出与{title}关联的笔记",
                    "find_related_notes",
                    note_key,
                    5,
                    note_key,
                    related_targets,
                ),
            ]
        )
    return rows


def _validate_and_deduplicate(rows: list[dict]) -> list[dict]:
    seen = set()
    valid_rows = []
    for item in rows:
        fingerprint = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if fingerprint in seen:
            continue
        PlannerDecision.model_validate(item["output"])
        seen.add(fingerprint)
        valid_rows.append(item)
    return valid_rows


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    serialized = []
    for item in rows:
        serialized.append(
            json.dumps(
                {**item, "output": json.dumps(item["output"], ensure_ascii=False, separators=(",", ":"))},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    path.write_text("\n".join(serialized) + ("\n" if serialized else ""), encoding="utf-8")


def validate_training_data(config: dict, data_dir: Path) -> dict[str, int]:
    """Validate registered Alpaca rows with the runtime planner contract."""
    info_path = data_dir / "dataset_info.json"
    manifest_path = data_dir / "manifest.json"
    if not info_path.is_file() or not manifest_path.is_file():
        raise ValueError("数据构建后缺少 dataset_info.json 或 manifest.json")
    info = json.loads(info_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("source") != "synthetic-template":
        raise ValueError("manifest 未标明 synthetic-template 来源")

    expected_columns = {"prompt": "instruction", "query": "input", "response": "output"}
    counts: dict[str, int] = {}
    for config_key in ("dataset", "eval_dataset"):
        name = config.get(config_key)
        registration = info.get(name) if isinstance(name, str) else None
        if not isinstance(registration, dict) or registration.get("columns") != expected_columns:
            raise ValueError(f"dataset_info.json 注册不匹配：{name}")
        path = data_dir / str(registration.get("file_name", ""))
        if not path.is_file():
            raise ValueError(f"数据集文件不存在：{path}")
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not rows:
            raise ValueError(f"数据集不能为空：{path}")
        for line_number, item in enumerate(rows, 1):
            if any(
                not isinstance(item.get(field), str) or not item[field].strip()
                for field in ("instruction", "input", "output")
            ):
                raise ValueError(f"{path}:{line_number} 缺少非空 Alpaca 字段")
            try:
                plan = json.loads(item["output"])
                PlannerDecision.model_validate(plan)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"{path}:{line_number} 未通过 PlannerDecision 严格校验"
                ) from exc
        counts[name] = len(rows)
    return counts


def build_dataset(vault: Path, output: Path, seed: int = 8503) -> dict[str, int]:
    """Create grouped train, validation, and test JSONL files from Markdown notes."""
    details = [
        (
            note.relative_path,
            note.title,
            next((tag for tag in note.tags if tag), note.title),
            note.links,
        )
        for note in scan_vault(vault)
    ]
    aliases: dict[str, str] = {}
    for note_key, title, _, _ in details:
        for alias in (
            title,
            Path(note_key).stem,
            note_key,
            note_key.removesuffix(".md"),
        ):
            aliases.setdefault(alias, note_key)
    note_keys_by_id = {_note_id(note_key): note_key for note_key, _, _, _ in details}
    source_rows = []
    for note_key, title, tag, links in details:
        related_note_keys = sorted(
            {aliases[item] for item in links if item in aliases and aliases[item] != note_key}
        )
        first_link = links[0] if links else None
        link_target_key = aliases.get(first_link) if first_link else None
        if link_target_key == note_key:
            link_target_key = None
        link = first_link if link_target_key else title
        source_rows.extend(
            _template_rows(
                note_key,
                title,
                tag,
                link,
                related_note_keys,
                link_target_key,
            )
        )

    dropped_cross_split_targets = 0
    split_safe_rows = []
    for item in source_rows:
        source_split = split_name(item["meta"]["group"])
        target_splits = {
            split_name(note_keys_by_id[target])
            for target in item["meta"]["target_note_ids"]
        }
        if any(target_split != source_split for target_split in target_splits):
            dropped_cross_split_targets += 1
            continue
        split_safe_rows.append(item)

    rows = _validate_and_deduplicate(split_safe_rows)
    random.Random(seed).shuffle(rows)
    grouped = {split: [] for split in SPLITS}
    for item in rows:
        grouped[split_name(item["meta"]["group"])].append(item)

    output.mkdir(parents=True, exist_ok=True)
    for split in SPLITS:
        _write_jsonl(output / f"{split}.jsonl", grouped[split])

    columns = {"prompt": "instruction", "query": "input", "response": "output"}
    _write_json(
        output / "dataset_info.json",
        {
            f"query_planner_{split}": {
                "file_name": f"{split}.jsonl",
                "formatting": "alpaca",
                "columns": columns,
            }
            for split in SPLITS
        },
    )

    stats = {split: len(grouped[split]) for split in SPLITS}
    stats["total"] = sum(stats.values())
    file_hashes = {
        name: hashlib.sha256((output / name).read_bytes()).hexdigest()
        for name in ("train.jsonl", "validation.jsonl", "test.jsonl", "dataset_info.json")
    }
    _write_json(
        output / "manifest.json",
        {
            "counts": stats,
            "dropped_cross_split_targets": dropped_cross_split_targets,
            "files": file_hashes,
            "seed": seed,
            "source": "synthetic-template",
        },
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=8503)
    args = parser.parse_args()
    print(json.dumps(build_dataset(args.vault, args.output, args.seed), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
