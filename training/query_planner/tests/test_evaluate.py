import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import httpx

from training.query_planner.evaluate import (
    load_verified_test_data,
    OpenAIChatEndpoint,
    publish_report_pair,
    score_rows,
    validate_target_metadata,
)


def _row(intent: str = "search_notes", targets: list[str] | None = None) -> dict:
    resolved_targets = ["rag-id"] if targets is None else targets
    return {
        "input": "查找 RAG",
        "output": json.dumps(
            {"intent": intent, "query": "RAG", "top_k": 3},
            ensure_ascii=False,
        ),
        "meta": {
            "group": "技术/RAG.md",
            "source_note_id": "rag-id",
            "target_note_ids": resolved_targets,
        },
    }


def test_score_rows_keeps_schema_intent_parameters_and_fallback_independent():
    rows = [_row(), _row("open_note"), _row("open_note")]
    outputs = [
        '{"intent":"search_notes","query":"RAG","top_k":3}',
        '{"intent":"open_note","query":"RAG","top_k":99}',
        '{"intent":"open_note","query":"../secret.md","top_k":1}',
    ]

    report = score_rows(
        rows,
        outputs,
        retrieved_note_ids=[["other", "rag-id"], ["rag-id"], []],
        latencies_ms=[12.5, 20.0, 3.0],
    )

    assert report.sample_count == 3
    assert report.schema_valid_rate == pytest.approx(2 / 3)
    assert report.intent_accuracy == 1.0
    assert report.parameter_constraint_rate == pytest.approx(2 / 3)
    assert report.fallback_rate == pytest.approx(2 / 3)
    assert report.recall_at_3 == pytest.approx(2 / 3)
    assert report.items[1].schema_valid is False
    assert report.items[1].used_fallback is True
    assert report.items[1].parameter_constraints_valid is False
    assert report.items[1].parsed_decision == {
        "intent": "search_notes",
        "query": "查找 RAG",
        "top_k": 3,
    }
    assert report.items[1].raw_output == outputs[1]
    assert report.items[1].retrieved_note_ids == ["rag-id"]
    assert report.items[1].target_hit is True
    assert report.items[1].latency_ms == 20.0
    assert report.items[2].schema_valid is True
    assert report.items[2].parameter_constraints_valid is True
    assert report.items[2].used_fallback is True


def test_extra_field_only_invalidates_schema_not_intent_or_parameter_metrics():
    report = score_rows(
        [_row()],
        ['{"intent":"search_notes","query":"RAG","top_k":3,"extra":true}'],
        retrieved_note_ids=[[]],
        latencies_ms=[1.0],
    )

    assert report.schema_valid_rate == 0.0
    assert report.intent_accuracy == 1.0
    assert report.parameter_constraint_rate == 1.0
    assert report.fallback_rate == 1.0


def test_score_rows_uses_real_retrieval_results_and_explicit_recall_denominator():
    without_target = _row("find_related_notes", targets=[])
    without_target["meta"]["target_note_ids"] = []
    report = score_rows(
        [_row(), without_target],
        [
            '{"intent":"search_notes","query":"RAG","top_k":3}',
            '{"intent":"find_related_notes","query":"技术/RAG.md","top_k":3}',
        ],
        retrieved_note_ids=[["not-the-gold-plan"], ["anything"]],
        latencies_ms=[1.0, 2.0],
    )

    assert report.recall_at_3 == 0.0
    assert report.recall_sample_count == 1
    assert report.items[0].target_hit is False
    assert report.items[1].target_hit is None


def test_old_row_without_explicit_targets_is_excluded_from_recall():
    row = _row()
    row["meta"].pop("target_note_ids")
    report = score_rows(
        [row],
        ['{"intent":"search_notes","query":"RAG","top_k":3}'],
        retrieved_note_ids=[["would-have-matched-derived-group"]],
        latencies_ms=[1.0],
    )

    assert report.recall_sample_count == 0
    assert report.items[0].target_note_ids == []
    assert report.items[0].target_hit is None


def test_score_rows_empty_input_has_zero_rates_and_rejects_length_mismatch():
    empty = score_rows([], [], retrieved_note_ids=[], latencies_ms=[])
    assert empty.sample_count == 0
    assert empty.recall_sample_count == 0
    assert empty.schema_valid_rate == 0.0
    assert empty.recall_at_3 == 0.0

    with pytest.raises(ValueError, match="数量必须一致"):
        score_rows([_row()], [], retrieved_note_ids=[], latencies_ms=[])


def test_load_verified_test_data_reads_the_hashed_bytes(tmp_path: Path):
    data = tmp_path / "test.jsonl"
    manifest = tmp_path / "manifest.json"
    payload = (json.dumps(_row(), ensure_ascii=False) + "\n").encode("utf-8")
    data.write_bytes(payload)
    manifest.write_text(
        json.dumps(
            {
                "counts": {"test": 1},
                "files": {"test.jsonl": hashlib.sha256(payload).hexdigest()},
                "seed": 7,
            }
        ),
        encoding="utf-8",
    )

    loaded = load_verified_test_data(data, manifest)

    assert loaded.sha256 == hashlib.sha256(payload).hexdigest()
    assert loaded.seed == 7
    assert loaded.sample_count == 1
    assert loaded.rows[0]["input"] == "查找 RAG"


@pytest.mark.parametrize("failure", ["hash", "count", "empty"])
def test_load_verified_test_data_fails_closed(tmp_path: Path, failure: str):
    data = tmp_path / "test.jsonl"
    manifest = tmp_path / "manifest.json"
    payload = b"" if failure == "empty" else (json.dumps(_row()) + "\n").encode()
    data.write_bytes(payload)
    digest = "0" * 64 if failure == "hash" else hashlib.sha256(payload).hexdigest()
    count = 2 if failure == "count" else (0 if failure == "empty" else 1)
    manifest.write_text(
        json.dumps({"counts": {"test": count}, "files": {"test.jsonl": digest}, "seed": 7}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_verified_test_data(data, manifest)


def test_publish_report_pair_writes_both_or_neither(tmp_path: Path, monkeypatch):
    prefix = tmp_path / "query-planner-base"
    payload = {
        "metadata": {
            "model": "base-model",
            "data_sha256": "a" * 64,
            "manifest_seed": 7,
            "latency_ms": {"mean": 1.0},
        },
        "metrics": {
            "sample_count": 1,
            "recall_sample_count": 1,
            "schema_valid_rate": 1.0,
            "intent_accuracy": 1.0,
            "parameter_constraint_rate": 1.0,
            "recall_at_3": 1.0,
            "fallback_rate": 0.0,
        },
        "items": [],
    }

    json_path, md_path = publish_report_pair(prefix, payload)
    assert json_path.exists() and md_path.exists()
    assert json.loads(json_path.read_text(encoding="utf-8"))["metadata"]["model"] == "base-model"

    bad_prefix = tmp_path / "bad-report"
    with pytest.raises(KeyError):
        publish_report_pair(bad_prefix, {"metadata": {}, "metrics": {}})
    assert not bad_prefix.with_suffix(".json").exists()
    assert not bad_prefix.with_suffix(".md").exists()

    original_replace = Path.replace

    def fail_markdown_publish(path: Path, target: Path):
        if path.name.endswith(".tmp") and ".md." in path.name:
            raise OSError("simulated publish failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_markdown_publish)
    failed_prefix = tmp_path / "failed-pair"
    with pytest.raises(OSError, match="simulated"):
        publish_report_pair(failed_prefix, payload)
    assert not failed_prefix.with_suffix(".json").exists()
    assert not failed_prefix.with_suffix(".md").exists()


def test_cli_target_validation_requires_existing_group_and_target_ids():
    class FakeService:
        def read(self, relative_path: str):
            if relative_path != "技术/RAG.md":
                raise KeyError(relative_path)
            return SimpleNamespace(note_id="rag-id")

        def read_by_id(self, note_id: str):
            if note_id != "rag-id":
                raise KeyError(note_id)

    validate_target_metadata([_row()], FakeService())

    escaped = _row()
    escaped["meta"]["group"] = "../secret.md"
    with pytest.raises(ValueError, match="group"):
        validate_target_metadata([escaped], FakeService())

    missing = _row(targets=["missing-id"])
    with pytest.raises(ValueError, match="target_note_ids"):
        validate_target_metadata([missing], FakeService())


@pytest.mark.asyncio
async def test_openai_endpoint_strictly_records_served_model():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "model": "served-public-name",
                "choices": [{"message": {"content": "{}"}}],
            },
        )

    endpoint = OpenAIChatEndpoint("http://planner/v1", "requested", None, 1.0)
    await endpoint.close()
    endpoint._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        assert await endpoint.complete("查找 RAG") == "{}"
        assert endpoint.observed_models == ["served-public-name"]
    finally:
        await endpoint.close()
