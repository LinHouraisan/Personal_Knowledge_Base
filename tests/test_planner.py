import json
from pathlib import Path

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from app.agent import KnowledgeAgent
from app.config import Settings
from app.index import JsonVectorIndex
from app.knowledge import KnowledgeService
from app.planner import (
    OpenAICompatiblePlanner,
    PlannerDecision,
    dispatch_decision,
    parse_decision,
)


class FakeEmbedder:
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float("RAG" in text), float("向量" in text)] for text in texts]

    async def aembed_query(self, text: str) -> list[float]:
        return [float("RAG" in text), float("向量" in text)]


class FakeRunner:
    def __init__(self, answer: str):
        self.answer = answer
        self.payloads: list[dict[str, object]] = []

    async def ainvoke(self, payload: dict[str, object]) -> dict[str, object]:
        self.payloads.append(payload)
        return {"messages": [AIMessage(content=self.answer)]}


class SearchCallingFakeRunner(FakeRunner):
    def __init__(self, tools):
        super().__init__("根据检索证据，方案使用 RAG。")
        self.tools = {item.name: item for item in tools}

    async def ainvoke(self, payload: dict[str, object]) -> dict[str, object]:
        await self.tools["search_notes"].ainvoke({"query": "RAG", "top_k": 3})
        return await super().ainvoke(payload)


class FakePlanner:
    def __init__(self, raw: str | Exception):
        self.raw = raw

    async def plan(self, question: str) -> str:
        if isinstance(self.raw, Exception):
            raise self.raw
        return self.raw


class FakeChatModel:
    def __init__(self, content: str):
        self.content = content
        self.messages = None

    async def ainvoke(self, messages):
        self.messages = messages
        return AIMessage(content=self.content)


class CountingService:
    def __init__(self, service: KnowledgeService):
        self.service = service
        self.search_calls = 0
        self.read_calls = 0
        self.related_calls = 0

    async def search(self, query: str, top_k: int):
        self.search_calls += 1
        return await self.service.search(query, top_k)

    def read(self, relative_path: str):
        self.read_calls += 1
        return self.service.read(relative_path)

    def related(self, relative_path: str):
        self.related_calls += 1
        return self.service.related(relative_path)


@pytest_asyncio.fixture
async def service(vault: Path, tmp_path: Path) -> KnowledgeService:
    index = JsonVectorIndex(vault, tmp_path / "index.json", FakeEmbedder())
    knowledge = KnowledgeService(vault, "测试知识库", index)
    await knowledge.rebuild()
    return knowledge


def test_planner_decision_strips_query_and_forbids_extra_fields():
    decision = PlannerDecision(
        intent="search_notes",
        query="  RAG ",
        top_k=3,
    )

    assert decision.query == "RAG"
    with pytest.raises(ValidationError):
        PlannerDecision(
            intent="search_notes",
            query="RAG",
            top_k=3,
            command="delete_note",
        )


@pytest.mark.parametrize(
    "raw",
    [
        "not-json",
        '```json\n{"intent":"search_notes","query":"RAG","top_k":3}\n```',
        '{"intent":"delete_note","query":"RAG","top_k":3}',
        '{"intent":"search_notes","query":"","top_k":3}',
        '{"intent":"search_notes","query":"RAG","top_k":0}',
        '{"intent":"search_notes","query":"RAG","top_k":"3"}',
        '{"intent":"search_notes","query":"RAG","top_k":3,"tool":"read_note"}',
        '{"intent":"open_note","query":"../secret.md","top_k":3}',
        '{"intent":"open_note","query":"C:\\\\secret.md","top_k":3}',
        '{"intent":"open_note","query":"read_note(\"../../secret.md\")","top_k":3}',
    ],
)
def test_invalid_planner_output_falls_back_to_original_search(raw: str):
    decision, used_fallback = parse_decision(raw, "查一下RAG")

    assert used_fallback is True
    assert decision == PlannerDecision(
        intent="search_notes",
        query="查一下RAG",
        top_k=3,
    )


def test_valid_planner_output_is_accepted():
    raw = json.dumps(
        {"intent": "open_note", "query": "  项目/RAG 方案.md  ", "top_k": 1},
        ensure_ascii=False,
    )

    decision, used_fallback = parse_decision(raw, "打开RAG方案")

    assert used_fallback is False
    assert decision == PlannerDecision(
        intent="open_note",
        query="项目/RAG 方案.md",
        top_k=1,
    )


@pytest.mark.asyncio
async def test_dispatch_open_note_uses_knowledge_service_boundary(
    service: KnowledgeService,
):
    sources = await dispatch_decision(
        service,
        PlannerDecision(
            intent="open_note",
            query="项目/RAG 方案.md",
            top_k=1,
        ),
    )

    assert [source.relative_path for source in sources] == ["项目/RAG 方案.md"]


@pytest.mark.asyncio
async def test_planner_request_prompt_requires_json_only():
    model = FakeChatModel(
        '{"intent":"search_notes","query":"RAG","top_k":3}'
    )
    planner = OpenAICompatiblePlanner(model)

    raw = await planner.plan("查找 RAG")

    assert raw == '{"intent":"search_notes","query":"RAG","top_k":3}'
    assert model.messages[0]["role"] == "system"
    assert "只输出JSON" in model.messages[0]["content"]
    assert model.messages[1] == {"role": "user", "content": "查找 RAG"}


@pytest.mark.asyncio
async def test_disabled_planner_preserves_current_agent_behavior(
    service: KnowledgeService,
):
    runner = FakeRunner("没有调用工具。")
    agent = KnowledgeAgent(
        service,
        runner_factory=lambda tools: runner,
    )

    result = await agent.answer("RAG 是什么？")

    assert result.status == "no_evidence"
    assert result.sources == []


@pytest.mark.asyncio
async def test_planner_request_failure_preserves_current_agent_flow(
    service: KnowledgeService,
):
    counted = CountingService(service)
    tool_runner_creations = 0

    def tool_runner_factory(tools):
        nonlocal tool_runner_creations
        tool_runner_creations += 1
        return SearchCallingFakeRunner(tools)

    agent = KnowledgeAgent(
        counted,
        runner_factory=tool_runner_factory,
        planner=FakePlanner(RuntimeError("planner unavailable")),
        answer_runner_factory=lambda: pytest.fail(
            "Planner 请求失败时不应创建无工具回答 runner"
        ),
    )

    result = await agent.answer("RAG 是什么？")

    assert result.status == "answered"
    assert result.sources
    assert tool_runner_creations == 1
    assert counted.search_calls == 1


@pytest.mark.asyncio
async def test_invalid_planner_response_runs_safe_search_fallback(
    service: KnowledgeService,
):
    counted = CountingService(service)
    answer_runner = FakeRunner("根据预检索证据回答。")
    agent = KnowledgeAgent(
        counted,
        runner_factory=lambda tools: pytest.fail(
            "Planner 完成后不应创建工具型 runner"
        ),
        planner=FakePlanner("not-json"),
        answer_runner_factory=lambda: answer_runner,
    )

    result = await agent.answer("RAG")

    assert result.status == "answered"
    assert result.sources
    assert counted.search_calls == 1
    assert counted.read_calls == 0
    assert counted.related_calls == 0
    assert "只读预检索证据" in str(answer_runner.payloads[0])


@pytest.mark.asyncio
async def test_valid_planner_dispatches_once_and_never_creates_tool_runner(
    service: KnowledgeService,
):
    counted = CountingService(service)
    answer_runner = FakeRunner("根据受限规划器证据回答。")
    agent = KnowledgeAgent(
        counted,
        runner_factory=lambda tools: pytest.fail(
            "Planner 完成后不应创建工具型 runner"
        ),
        planner=FakePlanner(
            '{"intent":"search_notes","query":"RAG","top_k":3}'
        ),
        answer_runner_factory=lambda: answer_runner,
    )

    result = await agent.answer("RAG 是什么？")

    assert result.status == "answered"
    assert counted.search_calls == 1
    assert counted.read_calls == 0
    assert counted.related_calls == 0
    assert len(answer_runner.payloads) == 1


@pytest.mark.asyncio
async def test_planner_with_no_sources_does_not_call_answer_model(
    service: KnowledgeService,
):
    counted = CountingService(service)
    agent = KnowledgeAgent(
        counted,
        runner_factory=lambda tools: pytest.fail(
            "Planner 完成后不应创建工具型 runner"
        ),
        planner=FakePlanner(
            '{"intent":"search_notes","query":"不存在的内容","top_k":3}'
        ),
        answer_runner_factory=lambda: pytest.fail(
            "没有证据时不应创建回答 runner"
        ),
    )

    result = await agent.answer("不存在的内容")

    assert result.status == "no_evidence"
    assert result.sources == []
    assert counted.search_calls == 1


def test_planner_settings_are_disabled_and_secretless_by_default():
    settings = Settings(_env_file=None)

    assert settings.planner_enabled is False
    assert settings.planner_api_key is None
    assert settings.planner_base_url == "http://127.0.0.1:8001/v1"
    assert settings.planner_model == "qwen2.5-3b-query-planner"
    assert settings.planner_timeout_seconds == 10.0
