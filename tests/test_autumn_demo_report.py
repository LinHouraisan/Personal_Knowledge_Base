import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.demo import create_demo_app


def test_report_cli_uses_real_demo_responses(tmp_path):
    result = subprocess.run([sys.executable, "-m", "tools.autumn_demo_report", "--out", str(tmp_path)],
                            capture_output=True, text=True, cwd=Path(__file__).parents[1])
    assert result.returncode == 0, result.stderr
    run = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert run["mode"] == "synthetic_offline" and run["model_evaluation"] == "not_run"
    assert len(run["scenarios"]) == 3 and all(item["passed"] for item in run["scenarios"])
    with TestClient(create_demo_app()) as client:
        for item in run["scenarios"]:
            request = json.loads((tmp_path / (item["id"] + ".request.json")).read_text(encoding="utf-8"))
            body = client.post("/v1/career/report", json={"jd_text": request["jd_text"]}).json()
            assert body == json.loads((tmp_path / (item["id"] + ".json")).read_text(encoding="utf-8"))
            assert body["markdown"] == (tmp_path / (item["id"] + ".md")).read_text(encoding="utf-8")
            assert len(item["request_sha256"]) == 64
