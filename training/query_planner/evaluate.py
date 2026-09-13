"""Evaluate one query-planner endpoint on one verified test split."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.knowledge import KnowledgeService
from app.planner import (
    PLANNER_PROMPT,
    PlannerDecision,
    dispatch_decision,
    parse_decision,
)


class EvaluationItem(BaseModel):
    input: str
    gold: dict[str, object]
    target_note_ids: list[str]
    raw_output: str
    schema_valid: bool
    parameter_constraints_valid: bool
    parsed_decision: dict[str, object]
    used_fallback: bool
    retrieved_note_ids: list[str]
    target_hit: bool | None
    latency_ms: float = Field(ge=0)


class EvaluationReport(BaseModel):
    sample_count: int
    recall_sample_count: int
    schema_valid_rate: float
    intent_accuracy: float
    parameter_constraint_rate: float
    recall_at_3: float
    fallback_rate: float
    items: list[EvaluationItem]


@dataclass(frozen=True)
class VerifiedTestData:
    rows: list[dict]
    sha256: str
    seed: int
    sample_count: int


class PlannerEndpoint(Protocol):
    async def complete(self, question: str) -> str: ...


def _rate(numerator: int, denominator: int) -> float:
    """All empty-denominator rates are defined as 0.0."""
    return numerator / denominator if denominator else 0.0


def _gold_plan(row: dict) -> PlannerDecision:
    raw = row.get("output")
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
        return PlannerDecision.model_validate(payload)
    except (json.JSONDecodeError, TypeError, ValidationError) as exc:
        raise ValueError("测试集包含非法 gold 计划") from exc


def _raw_schema_valid(raw: str) -> bool:
    try:
        PlannerDecision.model_validate(json.loads(raw))
    except (json.JSONDecodeError, TypeError, ValidationError):
        return False
    return True


def _raw_intent_correct(raw: str, gold_intent: str) -> bool:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(payload, dict) and payload.get("intent") == gold_intent


def _raw_parameter_constraints_valid(raw: str) -> bool:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(payload, dict):
        return False
    query = payload.get("query")
    top_k = payload.get("top_k")
    return (
        isinstance(query, str)
        and 1 <= len(query.strip()) <= 200
        and type(top_k) is int
        and 1 <= top_k <= 5
    )


def _target_note_ids(row: dict) -> list[str]:
    meta = row.get("meta")
    if not isinstance(meta, dict):
        return []
    explicit = meta.get("target_note_ids")
    if isinstance(explicit, list):
        return [str(value) for value in explicit if str(value)]
    return []


def score_rows(
    rows: list[dict],
    raw_outputs: list[str],
    *,
    retrieved_note_ids: list[list[str]],
    latencies_ms: list[float],
) -> EvaluationReport:
    """Purely score supplied outputs and actual retrieval observations.

    Invalid model output is wrong for schema and intent even when runtime fallback
    happens to choose the gold intent. Recall uses post-dispatch observations and
    excludes rows without a reliable target from its denominator.
    """
    lengths = {
        len(rows),
        len(raw_outputs),
        len(retrieved_note_ids),
        len(latencies_ms),
    }
    if len(lengths) != 1:
        raise ValueError("rows、outputs、retrievals 和 latencies 数量必须一致")

    items: list[EvaluationItem] = []
    schema_count = intent_count = parameter_count = fallback_count = 0
    recall_hits = recall_denominator = 0
    for row, raw, retrieved, latency in zip(
        rows, raw_outputs, retrieved_note_ids, latencies_ms, strict=True
    ):
        gold = _gold_plan(row)
        schema_valid = _raw_schema_valid(raw)
        parameter_valid = _raw_parameter_constraints_valid(raw)
        decision, used_fallback = parse_decision(raw, str(row.get("input", "")))
        targets = _target_note_ids(row)
        top_three = list(dict.fromkeys(str(value) for value in retrieved))[:3]
        target_hit = bool(set(targets) & set(top_three)) if targets else None

        schema_count += int(schema_valid)
        intent_count += int(_raw_intent_correct(raw, gold.intent))
        parameter_count += int(parameter_valid)
        fallback_count += int(used_fallback)
        if target_hit is not None:
            recall_denominator += 1
            recall_hits += int(target_hit)

        items.append(
            EvaluationItem(
                input=str(row.get("input", "")),
                gold=gold.model_dump(),
                target_note_ids=targets,
                raw_output=raw,
                schema_valid=schema_valid,
                parameter_constraints_valid=parameter_valid,
                parsed_decision=decision.model_dump(),
                used_fallback=used_fallback,
                retrieved_note_ids=top_three,
                target_hit=target_hit,
                latency_ms=max(0.0, float(latency)),
            )
        )

    total = len(rows)
    return EvaluationReport(
        sample_count=total,
        recall_sample_count=recall_denominator,
        schema_valid_rate=_rate(schema_count, total),
        intent_accuracy=_rate(intent_count, total),
        parameter_constraint_rate=_rate(parameter_count, total),
        recall_at_3=_rate(recall_hits, recall_denominator),
        fallback_rate=_rate(fallback_count, total),
        items=items,
    )


def load_verified_test_data(test_path: Path, manifest_path: Path) -> VerifiedTestData:
    """Hash and parse the same byte snapshot; reject empty or inconsistent data."""
    payload = test_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = manifest.get("files", {}).get("test.jsonl")
    if not isinstance(expected, str) or digest != expected:
        raise ValueError("测试集 SHA-256 与 manifest 不一致")
    try:
        rows = [
            json.loads(line)
            for line in payload.decode("utf-8").splitlines()
            if line.strip()
        ]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("测试集不是合法 UTF-8 JSONL") from exc
    expected_count = manifest.get("counts", {}).get("test")
    if not rows:
        raise ValueError("测试集为空，拒绝生成报告")
    if type(expected_count) is not int or expected_count != len(rows):
        raise ValueError("测试集样本数与 manifest 不一致")
    seed = manifest.get("seed")
    if type(seed) is not int:
        raise ValueError("manifest 缺少合法 seed")
    for row in rows:
        _gold_plan(row)
    return VerifiedTestData(rows=rows, sha256=digest, seed=seed, sample_count=len(rows))


def validate_target_metadata(rows: list[dict], service: KnowledgeService) -> None:
    """Fail before endpoint calls if gold note references do not exist in the Vault."""
    for row in rows:
        meta = row.get("meta")
        if not isinstance(meta, dict) or not isinstance(meta.get("group"), str):
            raise ValueError("测试行缺少合法 meta.group")
        try:
            source_note = service.read(meta["group"])
        except (KeyError, ValueError):
            raise ValueError("meta.group 不是 Vault 中存在的安全相对路径") from None
        source_note_id = meta.get("source_note_id")
        if not isinstance(source_note_id, str) or not source_note_id:
            raise ValueError("测试行缺少 source_note_id，请重新生成数据")
        try:
            service.read_by_id(source_note_id)
        except KeyError:
            raise ValueError("source_note_id 在 Vault 中不存在") from None
        if source_note.note_id != source_note_id:
            raise ValueError("source_note_id 与 meta.group 不匹配")
        targets = meta.get("target_note_ids")
        if not isinstance(targets, list):
            raise ValueError("测试行缺少 target_note_ids，请重新生成数据")
        for note_id in targets:
            if not isinstance(note_id, str) or not note_id:
                raise ValueError("target_note_ids 必须是非空字符串列表")
            try:
                service.read_by_id(note_id)
            except KeyError:
                raise ValueError("target_note_ids 包含 Vault 中不存在的笔记") from None


class OpenAIChatEndpoint:
    def __init__(self, base_url: str, model: str, api_key: str | None, timeout: float):
        self.model = model
        self.observed_models: list[str] = []
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def complete(self, question: str) -> str:
        response = await self._client.post(
            self._url,
            headers=self._headers,
            json={
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": PLANNER_PROMPT},
                    {"role": "user", "content": question},
                ],
            },
        )
        response.raise_for_status()
        payload = response.json()
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("模型端点响应缺少 choices[0].message.content") from exc
        if not isinstance(content, str):
            raise ValueError("模型端点 content 必须是字符串")
        served_model = payload.get("model")
        if not isinstance(served_model, str) or not served_model.strip():
            raise ValueError("模型端点响应缺少公开 model 名")
        self.observed_models.append(served_model)
        return content


async def collect_observations(
    rows: list[dict], endpoint: PlannerEndpoint, service: KnowledgeService
) -> tuple[list[str], list[list[str]], list[float]]:
    """Call one planner endpoint and execute its validated/fallback read-only plan."""
    outputs: list[str] = []
    retrieved: list[list[str]] = []
    latencies: list[float] = []
    for row in rows:
        started = time.perf_counter()
        raw = await endpoint.complete(str(row.get("input", "")))
        decision, _ = parse_decision(raw, str(row.get("input", "")))
        try:
            sources = await dispatch_decision(service, decision)
        except (KeyError, ValueError):
            sources = []
        latencies.append((time.perf_counter() - started) * 1000)
        outputs.append(raw)
        retrieved.append([source.note_id for source in sources])
    return outputs, retrieved, latencies


def _markdown(payload: dict) -> str:
    metrics = payload["metrics"]
    metadata = payload["metadata"]
    return f"""# Query Planner 离线评测

> 本报告由真实端点运行生成；只能与使用同一 data_sha256 的报告比较。

- 模型：`{metadata['model']}`
- 数据 SHA-256：`{metadata['data_sha256']}`
- seed：`{metadata['manifest_seed']}`
- 样本数：`{metrics['sample_count']}`
- Schema 合法率：`{metrics['schema_valid_rate']:.4f}`
- 意图准确率：`{metrics['intent_accuracy']:.4f}`
- 参数约束通过率：`{metrics['parameter_constraint_rate']:.4f}`
- Recall@3：`{metrics['recall_at_3']:.4f}`（分母 {metrics['recall_sample_count']} 条）
- 回退率：`{metrics['fallback_rate']:.4f}`
- 平均端到端延迟：`{metadata['latency_ms']['mean']:.2f} ms`
"""


def publish_report_pair(output_prefix: Path, payload: dict) -> tuple[Path, Path]:
    """Publish JSON and Markdown as one recoverable pair."""
    json_path = output_prefix.with_suffix(".json")
    md_path = output_prefix.with_suffix(".md")
    json_bytes = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    md_bytes = _markdown(payload).encode("utf-8")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    temps = {
        json_path: json_path.with_name(f".{json_path.name}.{token}.tmp"),
        md_path: md_path.with_name(f".{md_path.name}.{token}.tmp"),
    }
    backups = {path: path.with_name(f".{path.name}.{token}.bak") for path in temps}
    moved: list[Path] = []
    committed = False
    try:
        temps[json_path].write_bytes(json_bytes)
        temps[md_path].write_bytes(md_bytes)
        for path, backup in backups.items():
            if path.exists():
                path.replace(backup)
        for path, temp in temps.items():
            temp.replace(path)
            moved.append(path)
        committed = True
    except Exception:
        for path in moved:
            path.unlink(missing_ok=True)
        for path, backup in backups.items():
            if backup.exists():
                backup.replace(path)
        raise
    finally:
        for path in temps.values():
            path.unlink(missing_ok=True)
        if committed:
            for path in backups.values():
                path.unlink(missing_ok=True)
    return json_path, md_path


def _latency_summary(values: list[float]) -> dict[str, float]:
    return {
        "mean": statistics.fmean(values) if values else 0.0,
        "median": statistics.median(values) if values else 0.0,
        "min": min(values) if values else 0.0,
        "max": max(values) if values else 0.0,
    }


async def _run(args: argparse.Namespace) -> None:
    from langchain_openai import OpenAIEmbeddings

    from app.index import JsonVectorIndex

    dataset = load_verified_test_data(args.test, args.manifest)
    embed_key = os.getenv(args.embedding_api_key_env)
    embedder = OpenAIEmbeddings(
        model=args.embedding_model,
        base_url=args.embedding_base_url,
        api_key=embed_key or "not-configured",
        check_embedding_ctx_length=False,
    )
    service = KnowledgeService(
        args.vault,
        args.vault_name,
        JsonVectorIndex(args.vault, args.index, embedder),
    )
    await service.load()
    if not service.status().index_ready:
        raise ValueError("索引未就绪；请先用同一 Vault 和 Embedding 配置重建索引")
    validate_target_metadata(dataset.rows, service)

    endpoint = OpenAIChatEndpoint(
        args.base_url,
        args.model,
        os.getenv(args.api_key_env),
        args.timeout,
    )
    try:
        raw, retrieved, latencies = await collect_observations(
            dataset.rows, endpoint, service
        )
    finally:
        await endpoint.close()
    served_models = set(endpoint.observed_models)
    if len(served_models) != 1:
        raise ValueError("同一评测返回了多个 endpoint model 名，拒绝发布")
    endpoint_model = served_models.pop()
    report = score_rows(
        dataset.rows,
        raw,
        retrieved_note_ids=retrieved,
        latencies_ms=latencies,
    )
    payload = {
        "metadata": {
            "model": endpoint_model,
            "requested_model": args.model,
            "data_sha256": dataset.sha256,
            "manifest_seed": dataset.seed,
            "manifest_sample_count": dataset.sample_count,
            "generated_at": datetime.now(UTC).isoformat(),
            "latency_ms": _latency_summary(latencies),
        },
        "metrics": report.model_dump(exclude={"items"}),
        "items": [item.model_dump() for item in report.items],
    }
    json_path, md_path = publish_report_pair(args.output_prefix, payload)
    print(f"已生成真实评测报告：{json_path} 和 {md_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--test",
        type=Path,
        default=Path("training/query_planner/data/test.jsonl"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("training/query_planner/data/manifest.json"),
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help="本次只调用的一个 OpenAI-compatible chat /v1 地址",
    )
    parser.add_argument("--model", required=True, help="写入报告的公开模型名")
    parser.add_argument("--api-key-env", default="PLANNER_API_KEY")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--vault", type=Path, default=Path("sample_vault"))
    parser.add_argument("--vault-name", default="个人知识库示例")
    parser.add_argument("--index", type=Path, default=Path("data/index.json"))
    parser.add_argument("--embedding-base-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--embedding-model", default="bge-m3")
    parser.add_argument("--embedding-api-key-env", default="EMBEDDING_API_KEY")
    parser.add_argument("--output-prefix", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
