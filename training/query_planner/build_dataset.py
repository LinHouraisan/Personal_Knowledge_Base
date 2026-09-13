"""Build deterministic, template-synthetic data for read-only query planning."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


ALLOWED_INTENTS = {"search_notes", "open_note", "find_related_notes"}
SPLITS = ("train", "validation", "test")
INSTRUCTION = "将请求转换为只读知识库查询计划，只输出JSON。"


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["search_notes", "open_note", "find_related_notes"]
    query: str = Field(min_length=1)
    top_k: int = Field(ge=1, le=5)


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
    return {
        "instruction": INSTRUCTION,
        "input": prompt,
        "output": {"intent": intent, "query": query.strip(), "top_k": top_k},
        "meta": {
            "group": note_key,
            "source": "synthetic-template",
            "target_note_ids": target_note_ids,
        },
    }


def _note_details(path: Path, vault: Path) -> tuple[str, str, str, str]:
    text = path.read_text(encoding="utf-8")
    note_key = path.relative_to(vault).as_posix()
    frontmatter = {}
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if match:
        loaded = yaml.safe_load(match.group(1))
        if isinstance(loaded, dict):
            frontmatter = loaded
        text = text[match.end() :]

    heading = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
    title = heading.group(1).strip() if heading else path.stem
    tags = frontmatter.get("tags", [])
    if tags is None:
        tags = []
    elif not isinstance(tags, list):
        tags = [tags]
    tag = next((str(value).strip() for value in tags if str(value).strip()), title)
    link = next((value.strip() for value in re.findall(r"\[\[([^\]|#]+)", text) if value.strip()), title)
    return note_key, title, tag, link


def _template_rows(
    note_key: str,
    title: str,
    tag: str,
    link: str,
    related_note_key: str | None,
) -> list[dict]:
    own_target = [_note_id(note_key)]
    related_target = [_note_id(related_note_key)] if related_note_key else []
    return [
        row(
            f"搜索与{title}相关的笔记",
            "search_notes",
            title,
            3,
            note_key,
            own_target,
        ),
        row(
            f"查找标签{tag}的笔记",
            "search_notes",
            tag,
            3,
            note_key,
            own_target,
        ),
        row(f"打开{title}", "open_note", note_key, 1, note_key, own_target),
        row(
            f"找出与{title}关联的笔记",
            "find_related_notes",
            note_key,
            5,
            note_key,
            related_target,
        ),
        row(
            f"修改{title}并写入知识库",
            "search_notes",
            title,
            3,
            note_key,
            own_target,
        ),
        row(
            f"检索{link}的相关资料",
            "search_notes",
            link,
            3,
            note_key,
            related_target or own_target,
        ),
    ]


def _validate_and_deduplicate(rows: list[dict]) -> list[dict]:
    seen = set()
    valid_rows = []
    for item in rows:
        fingerprint = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if fingerprint in seen:
            continue
        QueryPlan.model_validate(item["output"])
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


def build_dataset(vault: Path, output: Path, seed: int = 8503) -> dict[str, int]:
    """Create grouped train, validation, and test JSONL files from Markdown notes."""
    details = [_note_details(path, vault) for path in sorted(vault.rglob("*.md"))]
    aliases: dict[str, str] = {}
    for note_key, title, _, _ in details:
        for alias in (
            title,
            Path(note_key).stem,
            note_key,
            note_key.removesuffix(".md"),
        ):
            aliases.setdefault(alias, note_key)
    source_rows = []
    for note_key, title, tag, link in details:
        related_note_key = aliases.get(link)
        if related_note_key == note_key:
            related_note_key = None
        source_rows.extend(_template_rows(note_key, title, tag, link, related_note_key))

    rows = _validate_and_deduplicate(source_rows)
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
        {"counts": stats, "files": file_hashes, "seed": seed, "source": "synthetic-template"},
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
