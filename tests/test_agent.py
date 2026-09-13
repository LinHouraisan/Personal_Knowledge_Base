from pathlib import Path

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage

from app.agent import KnowledgeAgent, make_knowledge_tools
from app.index import JsonVectorIndex
from app.knowledge import KnowledgeService


class FakeEmbedder:
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float("RAG" in text), float("Embedding" in text)] for text in texts]

    async def aembed_query(self, text: str) -> list[float]:
        return [float("RAG" in text), float("Embedding" in text)]


class FakeRunner:
    def __init__(self, answer: str):
        self.answer = answer

    async def ainvoke(self, payload: dict[str, object]) -> dict[str, object]:
        return {"messages": [AIMessage(content=self.answer)]}


class SearchCallingFakeRunner:
    def __init__(self, tools, query: str):
        self.tools = {item.name: item for item in tools}
        self.query = query

    async def ainvoke(self, payload: dict[str, object]) -> dict[str, object]:
        await self.tools["search_notes"].ainvoke({"query": self.query, "top_k": 3})
        return {"messages": [AIMessage(content="根据检索证据，方案使用 RAG。")]} 


@pytest_asyncio.fixture
async def service(vault: Path, tmp_path: Path) -> KnowledgeService:
    index = JsonVectorIndex(vault, tmp_path / "index.json", FakeEmbedder())
    knowledge = KnowledgeService(vault, "测试知识库", index)
    await knowledge.rebuild()
    return knowledge


def test_agent_exposes_only_read_only_tools(service: KnowledgeService):
    tools = make_knowledge_tools(service, [])

    assert {tool.name for tool in tools} == {
        "search_notes",
        "read_note",
        "find_related_notes",
    }


@pytest.mark.asyncio
async def test_agent_without_tool_evidence_rejects_model_claim(service: KnowledgeService):
    agent = KnowledgeAgent(
        service,
        runner_factory=lambda tools: FakeRunner("数据库采用 PostgreSQL。"),
    )

    result = await agent.answer("数据库是什么？")

    assert result.status == "no_evidence"
    assert result.sources == []
    assert "无法从知识库确认" in result.answer
    assert "PostgreSQL" not in result.answer


@pytest.mark.asyncio
async def test_agent_returns_deduplicated_tool_sources(service: KnowledgeService):
    agent = KnowledgeAgent(
        service,
        runner_factory=lambda tools: SearchCallingFakeRunner(tools, query="RAG"),
    )

    result = await agent.answer("RAG 方案是什么？")

    assert result.status == "answered"
    assert result.answer == "根据检索证据，方案使用 RAG。"
    assert result.sources
    assert len({source.relative_path for source in result.sources}) == len(result.sources)


@pytest.mark.asyncio
async def test_each_answer_uses_an_isolated_evidence_list(service: KnowledgeService):
    calls = 0

    def factory(tools):
        nonlocal calls
        calls += 1
        return SearchCallingFakeRunner(tools, query="RAG") if calls == 1 else FakeRunner("旧证据不能复用")

    agent = KnowledgeAgent(service, runner_factory=factory)

    first = await agent.answer("RAG 是什么？")
    second = await agent.answer("另一个问题")

    assert first.status == "answered"
    assert second.status == "no_evidence"
    assert second.sources == []
