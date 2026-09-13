from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import AgentAnswer, IndexStats, KnowledgeStatus, NoteView, Source


class FakeService:
    async def load(self):
        return None

    def status(self):
        return KnowledgeStatus(
            vault_name="测试知识库",
            index_ready=True,
            notes=3,
            chunks=5,
        )

    async def search(self, query: str, top_k: int):
        return [
            Source(
                note_id="note-1",
                title="RAG 方案",
                relative_path="项目/RAG 方案.md",
                excerpt="只读知识库使用检索证据。",
                score=0.95,
                obsidian_uri="obsidian://open?vault=test&file=RAG.md",
            )
        ]

    async def rebuild(self):
        return IndexStats(notes=3, chunks=5, embedded=0, removed=0)

    def read_by_id(self, note_id: str):
        if note_id != "note-1":
            raise KeyError(note_id)
        return NoteView(
            note_id="note-1",
            title="RAG 方案",
            relative_path="项目/RAG 方案.md",
            content="只读知识库使用检索证据。",
            tags=["RAG"],
            links=[],
            obsidian_uri="obsidian://open?vault=test&file=RAG.md",
        )


class FakeAgent:
    async def answer(self, question: str):
        return AgentAnswer(
            status="no_evidence",
            answer="无法从知识库确认。",
            sources=[],
        )


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(
        vault_path=tmp_path,
        index_path=tmp_path / "index.json",
        _env_file=None,
    )
    with TestClient(
        create_app(settings=settings, service=FakeService(), agent=FakeAgent())
    ) as test_client:
        yield test_client


def test_health_reports_vault_and_index(client: TestClient):
    body = client.get("/health").json()

    assert body == {
        "status": "ok",
        "vault_name": "测试知识库",
        "index_ready": True,
        "notes": 3,
        "chunks": 5,
    }


def test_search_returns_clickable_obsidian_source(client: TestClient):
    response = client.get("/v1/search", params={"q": "RAG", "top_k": 3})

    assert response.status_code == 200
    assert response.json()["sources"][0]["obsidian_uri"].startswith("obsidian://open?")


def test_chat_preserves_no_evidence_status(client: TestClient):
    response = client.post("/v1/chat", json={"question": "不存在的答案"})

    assert response.status_code == 200
    assert response.json()["status"] == "no_evidence"


def test_note_endpoint_uses_indexed_id(client: TestClient):
    assert client.get("/v1/notes/note-1").status_code == 200
    assert client.get("/v1/notes/unknown").status_code == 404


def test_api_has_no_write_routes(client: TestClient):
    paths = set(client.app.openapi()["paths"])

    assert not any(
        word in path for path in paths for word in ("create", "update", "delete")
    )


def test_request_log_does_not_contain_question(client: TestClient, caplog):
    secret_question = "这段查询内容不应写进日志"

    client.get("/v1/search", params={"q": secret_question})

    assert secret_question not in caplog.text


def test_root_serves_local_interface(client: TestClient):
    response = client.get("/")

    assert response.status_code == 200
    assert "在 Obsidian 中打开" in response.text
