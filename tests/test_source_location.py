import pytest

from app.knowledge import KnowledgeService
from app.lexical import LexicalRetriever
from app.models import Source


@pytest.mark.asyncio
async def test_lexical_source_location_and_null_cosine(tmp_path):
    (tmp_path / "a.md").write_text("# 测试标题\n\nSQL 查询示例", encoding="utf-8")
    service = KnowledgeService(tmp_path, "test", LexicalRetriever(tmp_path))
    await service.load()
    source = (await service.search("SQL"))[0]
    assert source.chunk_id and source.heading == "测试标题"
    assert source.score is None
    assert service.read_by_id(source.note_id).content.endswith("SQL 查询示例")


def test_old_source_constructor():
    source = Source(note_id="n", title="t", relative_path="t.md", excerpt="e", obsidian_uri="obsidian://open?")
    assert source.chunk_id is None and source.heading is None
