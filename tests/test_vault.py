from pathlib import Path

import pytest

from app.vault import chunk_note, parse_note, safe_note_path, scan_vault


def test_parse_note_extracts_frontmatter_tags_and_wikilinks(vault: Path):
    note = parse_note(vault, vault / "项目" / "RAG 方案.md")

    assert note.title == "RAG 方案"
    assert note.relative_path == "项目/RAG 方案.md"
    assert note.frontmatter["status"] == "active"
    assert set(note.tags) >= {"AI", "RAG"}
    assert note.links == ["Embedding 选择", "项目复盘"]
    assert len(note.content_hash) == 64


def test_scan_ignores_obsidian_and_attachments(vault: Path):
    paths = {note.relative_path for note in scan_vault(vault)}

    assert "项目/RAG 方案.md" in paths
    assert not any(path.startswith(".obsidian/") for path in paths)
    assert not any(path.startswith("attachments/") for path in paths)


def test_safe_note_path_blocks_parent_escape(vault: Path):
    with pytest.raises(ValueError, match="Vault"):
        safe_note_path(vault, "../secret.md")


def test_chunk_keeps_source_metadata(vault: Path):
    note = parse_note(vault, vault / "项目" / "RAG 方案.md")
    chunks = chunk_note(note, max_chars=120)

    assert chunks
    assert all(chunk.relative_path == "项目/RAG 方案.md" for chunk in chunks)
    assert all(len(chunk.text) <= 120 for chunk in chunks)


def test_chunk_preserves_oversized_paragraph(vault: Path):
    path = vault / "长文.md"
    body = "甲" * 251
    path.write_text(f"# 长文\n\n{body}\n", encoding="utf-8")

    chunks = chunk_note(parse_note(vault, path), max_chars=100)

    assert "".join(chunk.text for chunk in chunks) == "# 长文" + body
