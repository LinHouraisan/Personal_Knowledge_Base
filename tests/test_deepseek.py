import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.deepseek import DeepSeekAssistant
from app.demo import ExtractiveDemoAgent
from app.knowledge import KnowledgeService
from app.lexical import LexicalRetriever
from app.main import create_app


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    vault = tmp_path / "notes"
    vault.mkdir()
    notes = {
        "early.md": "---\ndate: 2026-09-22\ntype: learning\ntopic: 阅读\n---\n# 读书记录\n我准备写一张论点卡，但今天还没有动笔。",
        "later.md": "---\ndate: 2026-09-29\ntype: learning\ntopic: 阅读\n---\n# 读书回顾\n今天已经写完第一张论点卡。下周准备请朋友核对出处，还没有约时间。",
        "other.md": "---\ndate: 2026-09-30\ntype: project\ntopic: 网站\n---\n# 不相关的项目\n网站菜单还没改。",
        "goal.md": "---\ndate: 2026-09-20\ntype: goal\ntopic: 阅读\n---\n# 学会有依据地读书\n希望能写清观点及出处。",
    }
    for name, text in notes.items():
        (vault / name).write_text(text, encoding="utf-8")
    calls, replies = [], []

    class FakeModel:
        def __init__(self, **kwargs):
            self.options = kwargs

        async def ainvoke(self, messages, **kwargs):
            calls.append((messages, kwargs, self.options))
            value = replies.pop(0)
            if isinstance(value, Exception):
                raise value
            return SimpleNamespace(content=value, response_metadata={"finish_reason": "stop"})

    monkeypatch.setattr("app.deepseek.ChatOpenAI", FakeModel)
    path = tmp_path / ".env"
    path.write_text("UNRELATED=keep\n", encoding="utf-8")
    ai = DeepSeekAssistant(path)
    service = KnowledgeService(vault, "虚构测试", LexicalRetriever(vault))
    app = create_app(Settings(_env_file=None, vault_path=vault), service, ExtractiveDemoAgent(service), demo_mode=True, ai=ai)
    with TestClient(app, client=("127.0.0.1", 5050), base_url="http://127.0.0.1") as client:
        yield client, ai, path, calls, replies
    assert {p.name: p.read_text(encoding="utf-8") for p in vault.glob("*.md")} == notes


def connect(setup):
    client, _, _, _, replies = setup
    replies.append("连接成功")
    response = client.post("/v1/ai/connection", json={"api_key": "test-secret-not-real", "model": "deepseek-flash"})
    assert response.status_code == 200
    return client


def point(note, quote="今天已经写完第一张论点卡。"):
    return {"subject": "论点卡", "detail": "第一张论点卡已完成，核对出处仍是计划。", "state": "completed", "note_id": note["id"], "quote": quote}


def test_connect_persists_without_exposing_key_and_keeps_other_settings(setup):
    client, ai, path, calls, _ = setup
    assert client.get("/v1/ai/connection").json()["configured"] is False
    connect(setup)
    body = client.get("/v1/ai/connection").json()
    assert body["configured"] is True and body["verified"] is True
    assert "test-secret-not-real" not in json.dumps(body)
    assert "UNRELATED=keep" in path.read_text(encoding="utf-8")
    assert DeepSeekAssistant(path).status()["configured"] is True
    assert calls[0][2]["base_url"] == "https://api.deepseek.com"
    assert calls[0][2]["max_retries"] == 0


def test_connection_rejects_cross_origin_and_redacts_invalid_input(setup):
    client, _, path, calls, _ = setup
    for headers in ({"Origin": "https://unrelated.example"}, {"Host": "unrelated.example"}):
        response = client.post("/v1/ai/connection", headers=headers, json={"api_key": "test-secret-not-real"})
        assert response.status_code == 403 and "test-secret" not in response.text
    response = client.post("/v1/ai/connection", json={"api_key": ["test-secret-not-real"], "model": "wrong"})
    assert response.status_code == 422 and "test-secret" not in response.text
    assert not calls and path.read_text(encoding="utf-8") == "UNRELATED=keep\n"


def test_selected_document_is_sent_to_model_and_quotes_resolve(setup):
    client = connect(setup)
    notes = client.get("/v1/workspace").json()["notes"]
    note = next(n for n in notes if n["path"] == "later.md")
    setup[4].append(json.dumps({"items": [point(note)], "actions": []}, ensure_ascii=False))
    response = client.post("/v1/ai/chat", json={"question": "这篇里有哪些进展？", "note_id": note["id"]})
    assert response.status_code == 200
    body = response.json()
    assert body["method"] == "deepseek" and "已完成" in body["answer"]
    assert body["sources"][0]["note_id"] == note["id"]
    sent = json.loads(setup[3][-1][0][1]["content"])
    assert len(sent["notes"]) == 1 and "第一张论点卡" in sent["notes"][0]["content"]
    assert "这篇里有哪些进展" in sent["question"]
    assert setup[3][-1][1]["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("bad", ["not json", "wrong-note", "invented-quote"])
def test_unusable_model_output_never_becomes_a_success(setup, bad):
    client = connect(setup)
    note = next(n for n in client.get("/v1/workspace").json()["notes"] if n["path"] == "later.md")
    item = point(note)
    if bad == "wrong-note": item["note_id"] = "outside-vault"
    if bad == "invented-quote": item["quote"] = "原文没有这个句子"
    setup[4].append("not json" if bad == "not json" else json.dumps({"items": [item]}))
    response = client.post("/v1/ai/chat", json={"question": "进展", "note_id": note["id"]})
    assert response.status_code == 502
    assert "原文没有这个句子" not in response.text


def test_ai_reflection_uses_only_dated_matching_notes_and_goal(setup):
    client = connect(setup)
    notes = client.get("/v1/workspace").json()["notes"]
    latest = next(n for n in notes if n["path"] == "later.md")
    goal = next(n for n in notes if n["type"] == "goal")
    setup[4].append(json.dumps({"items": [point(latest)], "actions": [{"text": "约一次出处核对", "reason": "记录中尚未约时间", "done_when": "确认核对时间", "note_id": latest["id"], "quote": "下周准备请朋友核对出处，还没有约时间。"}]}))
    response = client.post("/v1/ai/reflection", json={"mode": "plan", "goal_id": goal["id"], "start_date": "2026-09-25"})
    assert response.status_code == 200
    body = response.json()
    assert body["notes_count"] == 1 and body["method"] == "deepseek"
    assert body["actions"][0]["source"]["note_id"] == latest["id"]
    sent = json.loads(setup[3][-1][0][1]["content"])
    assert [n["id"] for n in sent["notes"]] == [latest["id"]]
    assert "观点及出处" in sent["goal"]
    count = len(setup[3])
    empty = client.post("/v1/ai/reflection", json={"start_date": "2030-01-01"})
    assert empty.json()["status"] == "no_evidence" and len(setup[3]) == count
    assert empty.json()["method"] == "no_evidence"
    assert any("未调用 AI" in warning for warning in empty.json()["warnings"])


def test_missing_key_and_failed_reconnection_do_not_fall_back_or_overwrite(setup):
    client, _, path, _, replies = setup
    assert client.post("/v1/ai/chat", json={"question": "阅读"}).status_code == 503
    connect(setup)
    before = path.read_bytes()
    replies.append(RuntimeError("provider error mentions test-secret-do-not-leak"))
    response = client.post("/v1/ai/connection", json={"api_key": "new-secret-do-not-save", "model": "deepseek-flash"})
    assert response.status_code == 502
    assert "secret" not in response.text and path.read_bytes() == before


def test_installed_sdk_sends_deepseek_json_request_without_network(monkeypatch):
    import asyncio
    import httpx
    import app.deepseek as module
    from langchain_openai import ChatOpenAI as RealChatOpenAI

    seen = []
    def handle(request):
        body = json.loads(request.content)
        seen.append(body)
        assert request.url.host == "api.deepseek.com"
        assert request.url.path == "/chat/completions"
        return httpx.Response(200, json={"id": "local-check", "object": "chat.completion", "created": 1,
            "model": "deepseek-flash", "choices": [{"index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": '{"items": [], "actions": []}'}}]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as transport:
            monkeypatch.setattr(module, "ChatOpenAI", lambda **kwargs: RealChatOpenAI(**kwargs, http_async_client=transport))
            model = module.model_client("not-a-real-key", "deepseek-flash")
            result = await module.invoke(model, [{"role": "user", "content": "请返回 JSON"}], response_format={"type": "json_object"}, max_tokens=200)
            assert json.loads(result)["items"] == []
    asyncio.run(run())
    assert seen[0]["thinking"] == {"type": "disabled"}
    assert seen[0]["response_format"] == {"type": "json_object"}
    assert seen[0]["model"] == "deepseek-flash"
