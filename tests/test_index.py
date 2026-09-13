from pathlib import Path

import pytest

from app.index import JsonVectorIndex


class FakeEmbedder:
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    async def aembed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> list[float]:
        return [float("RAG" in text), float("数据库" in text)]


class CountingEmbedder(FakeEmbedder):
    def __init__(self):
        self.document_count = 0

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_count += len(texts)
        return await super().aembed_documents(texts)


@pytest.mark.asyncio
async def test_rebuild_persists_and_retrieve_uses_memory(vault: Path, tmp_path: Path):
    index_path = tmp_path / "index.json"
    index = JsonVectorIndex(vault, index_path, FakeEmbedder())

    stats = await index.rebuild()
    index_path.unlink()
    hits = await index.retrieve("RAG", 1)

    assert stats.notes == 3
    assert hits[0].chunk.relative_path == "项目/RAG 方案.md"
    assert hits[0].score == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_rebuild_only_embeds_changed_notes(vault: Path, tmp_path: Path):
    embedder = CountingEmbedder()
    index = JsonVectorIndex(vault, tmp_path / "index.json", embedder)

    await index.rebuild()
    first_count = embedder.document_count
    stats = await index.rebuild()

    assert embedder.document_count == first_count
    assert stats.embedded == 0


@pytest.mark.asyncio
async def test_rebuild_removes_deleted_notes(vault: Path, tmp_path: Path):
    index = JsonVectorIndex(vault, tmp_path / "index.json", FakeEmbedder())
    await index.rebuild()

    (vault / "项目" / "RAG 方案.md").unlink()
    stats = await index.rebuild()

    assert stats.removed == 1
    assert await index.retrieve("RAG", 5) == []


@pytest.mark.asyncio
async def test_load_restores_a_persisted_index(vault: Path, tmp_path: Path):
    index_path = tmp_path / "index.json"
    await JsonVectorIndex(vault, index_path, FakeEmbedder()).rebuild()
    restored = JsonVectorIndex(vault, index_path, FakeEmbedder())

    await restored.load()

    assert restored.ready() is True
    assert (await restored.retrieve("RAG", 1))[0].chunk.title == "RAG 方案"


@pytest.mark.asyncio
async def test_corrupt_index_loads_as_not_ready(vault: Path, tmp_path: Path):
    index_path = tmp_path / "index.json"
    index_path.write_text("not json", encoding="utf-8")
    index = JsonVectorIndex(vault, index_path, FakeEmbedder())

    await index.load()

    assert index.ready() is False


@pytest.mark.asyncio
async def test_top_k_is_bounded(vault: Path, tmp_path: Path):
    index = JsonVectorIndex(vault, tmp_path / "index.json", FakeEmbedder())
    await index.rebuild()

    with pytest.raises(ValueError, match="top_k"):
        await index.retrieve("RAG", 0)
