from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.demo import ExtractiveDemoAgent
from app.knowledge import KnowledgeService
from app.lexical import LexicalRetriever
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    examples = {
        "old.md": "---\ndate: 2026-09-20\ntype: learning\ntopic: 学习方法\n---\n# 旧记录\n## 已完成\n- 旧练习：完成以前的练习。",
        "first.md": "---\ndate: 2026-09-25\ntype: learning\ntopic: 学习方法\n---\n# 第一次复盘\n## 已完成\n- 检索练习：完成两道检索练习。\n## 未解决\n- 复盘方法：不知道怎样区分计划和成果。\n## 下一步\n- 复盘方法：补一份对照表；完成标准：列出原文和判断。",
        "latest.md": "---\ndate: 2026-09-29\ntype: learning\ntopic: 学习方法\n---\n# 第二次复盘\n## 已完成\n- 复盘方法：已经补齐对照表。\n## 未解决\n- 来源核对：总结遗漏原文。\n## 下一步\n- 来源核对：核对三条结论；完成标准：每条结论都有原文。",
        "project.md": "---\ndate: 2026-09-30\ntype: project\ntopic: 个人知识库\n---\n# 项目记录\n## 已完成\n- 页面：打开了演示页面。",
        "undated.md": "---\ntype: learning\ntopic: 学习方法\n---\n# 无日期\n## 已完成\n- 未知时间：不应混入本周成果。",
        "goal.md": "---\ndate: 2026-09-22\ntype: goal\ntopic: 学习方法\n---\n# 学会有依据的复盘\n希望总结可以回到原笔记核对。",
    }
    for name, content in examples.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    service = KnowledgeService(tmp_path, "测试示例", LexicalRetriever(tmp_path))
    settings = Settings(_env_file=None, vault_path=tmp_path)
    with TestClient(create_app(settings, service, ExtractiveDemoAgent(service), demo_mode=True)) as api:
        yield api
    assert {p.name: p.read_text(encoding="utf-8") for p in tmp_path.glob("*.md")} == examples


def test_review_filters_dates_and_uses_latest_state_with_real_sources(client):
    response = client.post("/v1/reflection", json={"scope": "learning", "start_date": "2026-09-24", "end_date": "2026-10-01"})
    assert response.status_code == 200
    body = response.json()
    assert body["notes_count"] == 2
    sections = {section["key"]: section["items"] for section in body["sections"]}
    assert {item["subject"] for item in sections["completed"]} == {"检索练习", "复盘方法"}
    assert [item["subject"] for item in sections["open"]] == ["来源核对"]
    assert "无日期" in " ".join(body["warnings"])
    for section in body["sections"]:
        for item in section["items"]:
            original = client.get("/v1/notes/" + item["source"]["note_id"]).json()
            assert item["text"] in original["content"]


def test_plan_uses_goal_topic_and_only_unfinished_recorded_actions(client):
    workspace = client.get("/v1/workspace")
    assert workspace.status_code == 200
    goal = workspace.json()["goals"][0]
    body = client.post("/v1/reflection", json={"mode": "plan", "goal_id": goal["id"]}).json()
    assert body["goal"]["id"] == goal["id"]
    assert len(body["actions"]) == 1
    action = body["actions"][0]
    assert action["subject"] == "来源核对"
    assert action["text"] == "核对三条结论"
    assert action["done_when"] == "每条结论都有原文。"
    assert action["source"]["title"] == "第二次复盘"
    assert body["goal"]["source"]["title"] == "学会有依据的复盘"


def test_open_focus_and_empty_range_do_not_invent_results(client):
    body = client.post("/v1/reflection", json={"scope": "learning", "focus": "open"}).json()
    assert all(section["key"] != "completed" for section in body["sections"])
    empty = client.post("/v1/reflection", json={"start_date": "2030-01-01", "end_date": "2030-01-02"}).json()
    assert empty["status"] == "no_evidence"
    assert empty["actions"] == []
    assert empty["sections"] == []


@pytest.mark.parametrize("payload", [
    {"start_date": "2026-10-02", "end_date": "2026-09-01"},
    {"mode": "plan"},
    {"mode": "plan", "goal_id": "unknown"},
    {"scope": "not-a-scope"},
])
def test_invalid_reflection_input_is_rejected(client, payload):
    assert client.post("/v1/reflection", json=payload).status_code == 422
