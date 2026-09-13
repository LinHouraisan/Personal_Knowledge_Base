import hashlib
import re
from pathlib import Path

import yaml

from app.models import NoteChunk, VaultNote


IGNORED_DIRECTORIES = {".obsidian", ".trash", ".git", "attachments"}
_WIKILINK = re.compile(r"(?<!!)\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
_INLINE_TAG = re.compile(r"(?<![\w/])#([\w/-]+)")
_HEADING = re.compile(r"^#{1,6}\s+(.+)$")


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def safe_note_path(vault_root: Path, relative_path: str) -> Path:
    if Path(relative_path).is_absolute():
        raise ValueError("笔记路径必须位于 Vault 内")
    root = vault_root.resolve()
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("笔记路径越过 Vault 边界")
    return candidate


def _split_frontmatter(raw: str) -> tuple[dict[str, object], str]:
    if not raw.startswith("---\n"):
        return {}, raw
    closing = raw.find("\n---\n", 4)
    if closing < 0:
        return {}, raw
    try:
        parsed = yaml.safe_load(raw[4:closing]) or {}
    except yaml.YAMLError:
        parsed = {}
    return (parsed if isinstance(parsed, dict) else {}), raw[closing + 5 :]


def _frontmatter_tags(frontmatter: dict[str, object]) -> list[str]:
    value = frontmatter.get("tags", [])
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip().lstrip("#") for item in value.split(",")]
    if isinstance(value, list):
        return [str(item).strip().lstrip("#") for item in value]
    return [str(value).strip().lstrip("#")]


def parse_note(vault_root: Path, path: Path) -> VaultNote:
    root = vault_root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("笔记路径越过 Vault 边界")
    raw = resolved.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(raw)
    relative_path = resolved.relative_to(root).as_posix()
    heading = next(
        (match.group(1).strip() for line in body.splitlines() if (match := _HEADING.match(line))),
        None,
    )
    title = heading or resolved.stem
    tags = _unique(_frontmatter_tags(frontmatter) + _INLINE_TAG.findall(body))
    links = _unique([match.strip() for match in _WIKILINK.findall(body)])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    note_id = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:16]
    return VaultNote(
        id=note_id,
        title=title,
        relative_path=relative_path,
        content=body.strip(),
        frontmatter=frontmatter,
        tags=tags,
        links=links,
        modified_ns=resolved.stat().st_mtime_ns,
        content_hash=digest,
    )


def scan_vault(vault_root: Path) -> list[VaultNote]:
    root = vault_root.resolve()
    if not root.is_dir():
        raise ValueError(f"Vault 不存在或不是目录：{root}")
    notes: list[VaultNote] = []
    for path in sorted(root.rglob("*.md"), key=lambda item: item.as_posix()):
        relative_parts = path.relative_to(root).parts[:-1]
        if any(part.startswith(".") or part in IGNORED_DIRECTORIES for part in relative_parts):
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            continue
        resolved_parts = resolved.relative_to(root).parts[:-1]
        if any(part.startswith(".") or part in IGNORED_DIRECTORIES for part in resolved_parts):
            continue
        notes.append(parse_note(root, resolved))
    return notes


def _split_text(text: str, max_chars: int) -> list[str]:
    return [text[start : start + max_chars] for start in range(0, len(text), max_chars)]


def chunk_note(note: VaultNote, max_chars: int = 800) -> list[NoteChunk]:
    if max_chars < 1:
        raise ValueError("max_chars 必须大于 0")
    chunks: list[NoteChunk] = []
    current_heading: str | None = None
    parts = [part.strip() for part in re.split(r"\n\s*\n", note.content) if part.strip()]
    sequence = 0
    for part in parts:
        heading_match = _HEADING.match(part)
        if heading_match:
            current_heading = heading_match.group(1).strip()
        compact = "".join(line.strip() for line in part.splitlines())
        for piece in _split_text(compact, max_chars):
            chunk_id = hashlib.sha256(
                f"{note.id}:{sequence}:{piece}".encode("utf-8")
            ).hexdigest()[:20]
            chunks.append(
                NoteChunk(
                    id=chunk_id,
                    note_id=note.id,
                    title=note.title,
                    relative_path=note.relative_path,
                    heading=current_heading,
                    text=piece,
                    tags=note.tags,
                )
            )
            sequence += 1
    return chunks
