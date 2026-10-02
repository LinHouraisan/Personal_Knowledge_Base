import hashlib
import socket
from pathlib import Path

from fastapi.testclient import TestClient

from app.demo import create_demo_app


def tree_hash(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest() for p in path.rglob("*") if p.is_file()}


def test_demo_end_to_end_without_clients_network_or_vault_writes(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("External model/network forbidden in offline demo")
    monkeypatch.setattr("app.main.OpenAIEmbeddings", forbidden)
    monkeypatch.setattr("app.main.build_knowledge_agent", forbidden)
    # Windows asyncio uses a local socket pair internally; HTTP transports remain blocked.
    original_connect = socket.socket.connect
    def no_external_connect(sock, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return original_connect(sock, address)
        return forbidden()
    monkeypatch.setattr(socket.socket, "connect", no_external_connect)
    monkeypatch.setattr("httpx.HTTPTransport.handle_request", forbidden)
    monkeypatch.setattr("httpx.AsyncHTTPTransport.handle_async_request", forbidden)
    monkeypatch.setenv("VAULT_PATH", str(tmp_path / "private-do-not-read"))
    monkeypatch.setenv("PLANNER_ENABLED", "true")
    monkeypatch.chdir(tmp_path)
    vault = Path(__file__).parents[1] / "sample_vault"
    before = tree_hash(vault)
    with TestClient(create_demo_app()) as client:
        assert client.get("/v1/capabilities").json() == {
            "demo": True, "answer_mode": "extractive", "vault_origin": "synthetic"
        }
        assert client.get("/health").json()["notes"] == len(list(vault.rglob("*.md")))
        sources = client.get("/v1/search", params={"q": "RAG"}).json()["sources"]
        assert sources and sources[0]["score"] is None
        assert client.get("/v1/notes/" + sources[0]["note_id"]).status_code == 200
        answer = client.post("/v1/chat", json={"question": "RAG"}).json()
        assert answer["status"] == "answered" and answer["answer"].startswith("离线证据摘录，未调用生成模型")
        assert client.post("/v1/chat", json={"question": "zzzznotfound"}).json()["status"] == "no_evidence"
        report = client.post("/v1/career/report", json={"jd_text": "Python RAG SQL"}).json()
        assert report["report"]["recognized_count"] == 3 and report["markdown"]
        assert client.post("/v1/index/rebuild").json()["embedded"] == 0
    assert tree_hash(vault) == before
    assert not (tmp_path / "data" / "index.json").exists()


def test_demo_import_ignores_invalid_unused_production_settings(tmp_path):
    import os
    import subprocess
    import sys

    root = Path(__file__).parents[1]
    (tmp_path / ".env").write_text("PLANNER_TIMEOUT_SECONDS=invalid-unused-production-file\n", encoding="utf-8")
    code = (
        "from app.demo import create_demo_app; "
        "from fastapi.testclient import TestClient; "
        "client = TestClient(create_demo_app()); "
        "client.__enter__(); "
        "assert client.get('/v1/capabilities').json()['demo'] is True; "
        "client.__exit__(None, None, None)"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True,
                            env={**os.environ, "PYTHONPATH": str(root), "PLANNER_ENABLED": "invalid-unused-demo-setting"})
    assert result.returncode == 0, result.stderr
