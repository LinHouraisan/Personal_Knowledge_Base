import pytest

from app.lexical import LexicalRetriever, lexical_score, query_terms
from app.models import NoteChunk


def chunk(text="", **kwargs):
    return NoteChunk(id="c1", note_id="n1", title="", relative_path="a.md", text=text, **kwargs)


def test_terms_and_word_boundaries():
    assert {"c++", "c#", "react.js", "ts"} <= query_terms("Ｃ＋＋ C# React.js TS")
    assert {"数据清洗", "数据", "据清", "清洗"} <= query_terms("数据清洗")
    assert query_terms(" 的 ! ") == set()
    assert lexical_score("SQL", chunk("NoSQL")) == 0
    assert lexical_score("SQL", chunk("sql 查询")) == 1
    assert lexical_score("", chunk("SQL")) == 0


def test_weighted_fields():
    item = NoteChunk(id="c", note_id="n", title="RAG", relative_path="RAG.md", text="RAG", tags=["rag"])
    assert lexical_score("RAG", item) == 10


@pytest.mark.asyncio
async def test_lexical_stable_order_empty_and_removal(tmp_path):
    retriever = LexicalRetriever(tmp_path)
    assert not retriever.ready()
    await retriever.load()
    assert retriever.ready() and await retriever.retrieve("SQL", 3) == []
    for name in ["b", "a"]:
        (tmp_path / (name + ".md")).write_text("# 技术\n\nSQL", encoding="utf-8")
    stats = await retriever.rebuild()
    assert stats.embedded == 0 and stats.notes == 2
    assert [h.chunk.relative_path for h in await retriever.retrieve("SQL", 20)] == ["a.md", "b.md"]
    (tmp_path / "a.md").unlink()
    assert (await retriever.rebuild()).removed == 1
    for k in [0, 21]:
        with pytest.raises(ValueError, match="top_k"):
            await retriever.retrieve("SQL", k)
