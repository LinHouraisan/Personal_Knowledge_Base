import pytest

from app.index import JsonVectorIndex
from app.config import Settings


class FixedEmbedder:
    async def aembed_documents(self, texts):
        return [[1, 0] if "semantic" in t else [0.8, 0.6] if "common" in t else [-1, 0] for t in texts]

    async def aembed_query(self, query):
        return [1, 0]


# Twelve deterministic ranking contracts; fixed vectors are NOT model evaluation.
@pytest.mark.asyncio
@pytest.mark.parametrize("term", ["python", "fastapi", "react", "typescript", "sql", "postgresql",
                                  "rag", "embedding", "agent", "lora", "etl", "数据标注"])
async def test_rrf_promotes_joint_candidate_preserves_cosine(tmp_path, term):
    (tmp_path / "a.md").write_text("semantic", encoding="utf-8")
    (tmp_path / "b.md").write_text("common " + term, encoding="utf-8")
    (tmp_path / "c.md").write_text(term, encoding="utf-8")
    index = JsonVectorIndex(tmp_path, tmp_path / "index.json", FixedEmbedder(), mode="hybrid")
    await index.rebuild()
    hits = await index.retrieve(term, 20)
    assert [h.chunk.relative_path for h in hits] == ["b.md", "a.md", "c.md"]
    assert [h.score for h in hits] == pytest.approx([0.8, 1.0, -1.0])
    # Duplicate persisted rows must not count twice in fusion.
    index._records += index._records
    assert [h.chunk.id for h in await index.retrieve(term, 20)] == [h.chunk.id for h in hits]


@pytest.mark.asyncio
async def test_default_vector_and_embedding_failure(tmp_path):
    (tmp_path / "a.md").write_text("semantic", encoding="utf-8")
    (tmp_path / "b.md").write_text("SQL", encoding="utf-8")
    index = JsonVectorIndex(tmp_path, tmp_path / "index.json", FixedEmbedder())
    await index.rebuild()
    assert [h.chunk.relative_path for h in await index.retrieve("SQL", 20)] == ["a.md"]
    index.mode = "hybrid"
    async def unavailable(query):
        raise RuntimeError("embedding unavailable")
    index.embedder.aembed_query = unavailable
    with pytest.raises(RuntimeError, match="unavailable"):
        await index.retrieve("SQL", 3)


@pytest.mark.asyncio
async def test_hybrid_empty_and_top_k(tmp_path):
    index = JsonVectorIndex(tmp_path, tmp_path / "index.json", FixedEmbedder(), mode="hybrid")
    await index.load()
    assert await index.retrieve("SQL", 3) == []
    for k in [0, 21]:
        with pytest.raises(ValueError, match="top_k"):
            await index.retrieve("SQL", k)


def test_retrieval_setting(monkeypatch):
    monkeypatch.delenv("RETRIEVAL_MODE", raising=False)
    assert Settings(_env_file=None).retrieval_mode == "vector"
    monkeypatch.setenv("RETRIEVAL_MODE", "hybrid")
    assert Settings(_env_file=None).retrieval_mode == "hybrid"
