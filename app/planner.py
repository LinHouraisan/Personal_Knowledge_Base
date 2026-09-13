import json
import re
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.knowledge import KnowledgeService
from app.models import Source


PLANNER_PROMPT = """你是只读知识库查询规划器。只输出JSON，不要输出 Markdown 或解释。
格式为 {"intent":"search_notes","query":"...","top_k":3}。
intent 只能是 search_notes、open_note 或 find_related_notes；top_k 只能是 1 到 5。
用户要求写入、修改、移动或删除笔记时，改为 search_notes 的只读查询。"""


class PlannerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    intent: Literal["search_notes", "open_note", "find_related_notes"]
    query: str = Field(min_length=1, max_length=200)
    top_k: int = Field(default=3, ge=1, le=5)

    @field_validator("query", mode="before")
    @classmethod
    def strip_query(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class PlannerClient(Protocol):
    async def plan(self, question: str) -> str: ...


class ChatModel(Protocol):
    async def ainvoke(self, messages: list[dict[str, str]]) -> object: ...


class OpenAICompatiblePlanner:
    def __init__(self, model: ChatModel):
        self.model = model

    async def plan(self, question: str) -> str:
        response = await self.model.ainvoke(
            [
                {"role": "system", "content": PLANNER_PROMPT},
                {"role": "user", "content": question},
            ]
        )
        content = getattr(response, "content", "")
        return content if isinstance(content, str) else ""


def _unsafe_query(query: str) -> bool:
    if "\x00" in query:
        return True
    if re.search(r"(^|[\\/])\.\.([\\/]|$)", query):
        return True
    if re.match(r"^(?:[A-Za-z]:[\\/]|[\\/])", query):
        return True
    return bool(re.match(r"^[A-Za-z_][\w.]*\s*\(", query))


def _fallback_decision(original_query: str) -> PlannerDecision:
    query = original_query.strip()[:200] or "用户查询"
    return PlannerDecision(intent="search_notes", query=query, top_k=3)


def parse_decision(
    raw: str, original_query: str
) -> tuple[PlannerDecision, bool]:
    try:
        payload = json.loads(raw)
        decision = PlannerDecision.model_validate(payload)
        if _unsafe_query(decision.query):
            raise ValueError("unsafe planner query")
    except (json.JSONDecodeError, TypeError, ValidationError, ValueError):
        return _fallback_decision(original_query), True
    return decision, False


def _note_source(service: KnowledgeService, relative_path: str) -> Source:
    note = service.read(relative_path)
    return Source(
        note_id=note.note_id,
        title=note.title,
        relative_path=note.relative_path,
        excerpt=note.content[:240],
        obsidian_uri=note.obsidian_uri,
    )


async def dispatch_decision(
    service: KnowledgeService, decision: PlannerDecision
) -> list[Source]:
    async def search_notes() -> list[Source]:
        return await service.search(decision.query, decision.top_k)

    async def open_note() -> list[Source]:
        return [_note_source(service, decision.query)]

    async def find_related_notes() -> list[Source]:
        return service.related(decision.query)[: decision.top_k]

    handlers = {
        "search_notes": search_notes,
        "open_note": open_note,
        "find_related_notes": find_related_notes,
    }
    return await handlers[decision.intent]()
