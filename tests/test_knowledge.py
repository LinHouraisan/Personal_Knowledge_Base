from pathlib import Path

import pytest
import pytest_asyncio

from app.index import JsonVectorIndex
from app.knowledge import KnowledgeService


class FakeEmbedder:
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    async def aembed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> list[float]:
        return [float("RAG" in text), float("Embedding" in text or "向量" in text)]


@pytest_asyncio.fixture
async def service(vault: Path, tmp_path: Path) -> KnowledgeService:
    index = JsonVectorIndex(vault, tmp_path / "index.json", FakeEmbedder())
    knowledge = KnowledgeService(vault, "测试知识库", index)
    await knowledge.rebuild()
    return knowledge


@pytest.mark.asyncio
async def test_search_returns_structured_source_and_uri(service: KnowledgeService):
    hits = await service.search("RAG", 3)

    assert hits[0].relative_path == "项目/RAG 方案.md"
    assert hits[0].obsidian_uri.startswith("obsidian://open?")
    assert hits[0].excerpt


def test_related_follows_wikilinks_and_backlinks(service: KnowledgeService):
    related = service.related("项目/RAG 方案.md")
    paths = {item.relative_path for item in related}

    assert "技术/Embedding 选择.md" in paths
    assert "项目复盘.md" in paths


def test_read_by_id_returns_only_an_indexed_note(service: KnowledgeService):
    source = service.related("技术/Embedding 选择.md")[0]

    note = service.read_by_id(source.note_id)

    assert note.relative_path == "项目/RAG 方案.md"
    with pytest.raises(KeyError):
        service.read_by_id("not-indexed")


def test_read_rejects_absolute_paths(service: KnowledgeService, tmp_path: Path):
    with pytest.raises(ValueError, match="Vault"):
        service.read(str((tmp_path / "outside.md").resolve()))


def test_status_reports_cached_note_and_chunk_counts(service: KnowledgeService):
    status = service.status()

    assert status.vault_name == "测试知识库"
    assert status.index_ready is True
    assert status.notes == 3
    assert status.chunks >= 3
