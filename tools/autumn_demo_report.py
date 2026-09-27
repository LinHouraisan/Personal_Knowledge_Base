import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.career import CareerReport
from app.demo import create_demo_app

SCENARIOS = [
    ("ai-development", "AI 应用开发", "使用 Python、FastAPI 开发 RAG 应用，了解 Embedding 和 Agent。", 5),
    ("fullstack", "前后端开发", "使用 React、TypeScript 开发页面，能编写 SQL 并使用 PostgreSQL。", 4),
    ("data-workflow", "数据处理与标注", "使用 Python 和 SQL 完成 ETL，并整理文本数据标注样例。", 4),
]


def _write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def generate_report(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
    state = subprocess.run(["git", "status", "--porcelain", "--", "app", "tools"], cwd=root, capture_output=True, text=True)
    run = {
        "mode": "synthetic_offline", "model_evaluation": "not_run",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "code_version": {"commit": revision.stdout.strip() if revision.returncode == 0 else "unavailable",
                         "working_tree": "modified" if state.stdout.strip() else "clean" if state.returncode == 0 else "unavailable"},
        "scenarios": [],
    }
    with TestClient(create_demo_app(), raise_server_exceptions=False) as client:
        capabilities = client.get("/v1/capabilities")
        offline = capabilities.status_code == 200 and capabilities.json() == {
            "demo": True, "answer_mode": "extractive", "vault_origin": "synthetic"
        }
        for key, label, jd, expected in SCENARIOS:
            _write_json(out / (key + ".request.json"), {"label": label, "source": "public_synthetic", "jd_text": jd})
            response = client.post("/v1/career/report", json={"jd_text": jd})
            try:
                body = response.json()
            except ValueError:
                body = {"error": "Non-JSON response"}
            _write_json(out / (key + ".json"), body)
            item = {"id": key, "http_status": response.status_code,
                    "request_sha256": hashlib.sha256(jd.encode("utf-8")).hexdigest(),
                    "recognized_count": None, "with_evidence_count": None, "passed": False}
            markdown = "# 场景未通过\n\n请检查 run.json；未生成可用证据报告。\n"
            try:
                report = CareerReport.model_validate(body["report"])
                markdown = body["markdown"]
                if not isinstance(markdown, str) or not markdown.strip():
                    raise ValueError("Missing markdown")
                item.update(recognized_count=report.recognized_count, with_evidence_count=report.with_evidence_count,
                            passed=offline and response.status_code == 200 and report.recognized_count == expected)
            except (KeyError, TypeError, ValueError):
                pass
            (out / (key + ".md")).write_text(markdown, encoding="utf-8")
            run["scenarios"].append(item)
    _write_json(out / "run.json", run)
    lines = ["# 公开虚构岗位的离线证据报告", "", "词法检索与规则对照；未调用生成模型，未人工核验。", ""]
    lines += [f"- [{label}]({key}.md)" for key, label, _, _ in SCENARIOS]
    lines += ["", "结果以 run.json 的 passed 和 HTTP 状态为准。资料命中不等于个人能力。"]
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return run


def main() -> int:
    parser = argparse.ArgumentParser(description="通过真实离线 demo 路由生成三份公开样例报告")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run = generate_report(args.out)
    return 0 if all(item["passed"] for item in run["scenarios"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
