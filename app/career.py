import html
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.knowledge import KnowledgeService
from app.lexical import find_terms
from app.models import Source

# Frozen v1 vocabulary and deterministic suggestions; no model inference.
SKILLS = [
    ("python", "Python", ["python"], "一段可运行的数据处理脚本及输入输出"),
    ("fastapi", "FastAPI", ["fastapi"], "一个带输入校验和失败响应的接口及测试"),
    ("react", "React", ["react", "react.js", "reactjs"], "一个有加载和失败状态的组件示例"),
    ("typescript", "TypeScript", ["typescript", "ts"], "类型约束与编译检查记录"),
    ("sql", "SQL", ["sql", "结构化查询"], "一组查询及执行结果"),
    ("postgresql", "PostgreSQL", ["postgresql", "postgres"], "表结构、索引和查询计划记录"),
    ("rag", "RAG", ["rag", "检索增强生成"], "问题—来源片段—回答的评测案例"),
    ("embedding", "Embedding", ["embedding", "向量化", "文本向量"], "同集检索对照和实验条件"),
    ("agent", "Agent", ["agent", "智能体"], "工具调用参数与失败处理案例"),
    ("lora", "LoRA", ["lora", "低秩适配"], "训练配置与同条件对照，未实测不填收益"),
    ("etl", "ETL", ["etl", "数据清洗", "数据抽取"], "清洗、去重及重复运行结果"),
    ("data_labeling", "文本数据标注", ["数据标注", "文本标注"], "标签说明、样例和复核记录"),
]
LIMITATIONS = [
    "仅提取 12 项有限词表关键词，不能完整理解岗位要求；请核对原句，尤其是否定或可选要求。",
    "关键词资料命中不等于个人能力、项目经历或录用概率；未找到记录不代表不会。",
    "结果未经过人工核验；建议来自 keyword_evidence_v1 固定模板。",
]


class CareerRequest(BaseModel):
    jd_text: str = Field(min_length=1, max_length=12000)

    @field_validator("jd_text", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class RequirementEvidence(BaseModel):
    skill_id: str
    label: str
    matched_terms: list[str]
    jd_excerpt: str
    status: Literal["evidence_found", "not_recorded"]
    sources: list[Source]
    suggested_action: str


class CareerReport(BaseModel):
    method: Literal["keyword_evidence_v1"] = "keyword_evidence_v1"
    requirements: list[RequirementEvidence]
    recognized_count: int
    with_evidence_count: int
    coverage_ratio: float | None
    limitations: list[str]


def build_career_report(jd_text: str, service: KnowledgeService) -> CareerReport:
    found = []
    for skill_id, label, aliases, action in SKILLS:
        matches = find_terms(jd_text, aliases)
        if not matches:
            continue
        position = matches[0][0]
        sentence = next((m.group().strip() for m in re.finditer(r"[^。！？!?；;\n]+[。！？!?；;\n]?", jd_text)
                         if m.start() <= position < m.end()), jd_text.strip())
        sources = service.keyword_sources(aliases)
        found.append((position, RequirementEvidence(
            skill_id=skill_id, label=label,
            matched_terms=list(dict.fromkeys(term for _, _, term in matches)),
            jd_excerpt=sentence,
            status="evidence_found" if sources else "not_recorded",
            sources=sources,
            suggested_action=("核对已有记录并补齐：" if sources else "可通过以下交付物补充记录：") + action + "。",
        )))
    found.sort(key=lambda item: item[0])
    requirements = [item for _, item in found]
    covered = sum(bool(item.sources) for item in requirements)
    return CareerReport(requirements=requirements, recognized_count=len(requirements),
                        with_evidence_count=covered,
                        coverage_ratio=covered / len(requirements) if requirements else None,
                        limitations=LIMITATIONS)


def _md(text: str) -> str:
    escaped = html.escape(text, quote=True)
    escaped = re.sub(r"([\\*_\[\]{}()#+.!|>-])", r"\\\1", escaped)
    return escaped.replace(chr(96), "\\" + chr(96)).replace("\n", " ")


def career_report_markdown(report: CareerReport) -> str:
    coverage = f"{report.coverage_ratio:.1%}" if report.coverage_ratio is not None else "不适用（无识别项）"
    lines = ["# 岗位关键词证据对照", "", "方法：keyword_evidence_v1（规则匹配，无模型评审）",
             f"已识别关键词的资料覆盖率：{coverage}；资料命中 {report.with_evidence_count}/{report.recognized_count}", ""]
    for item in report.requirements:
        lines.extend([f"## {_md(item.label)}", "",
                      "状态：" + ("找到相关资料" if item.sources else "当前知识库未找到相关记录"),
                      "命中别名：" + "、".join(_md(term) for term in item.matched_terms),
                      "岗位原句：" + _md(item.jd_excerpt), "建议：" + _md(item.suggested_action), ""])
        for source in item.sources:
            lines.extend(["- 来源：" + _md(source.relative_path),
                          "  分块：" + _md(source.chunk_id or "未定位") + "；标题：" + _md(source.heading or source.title),
                          "  摘录：" + _md(source.excerpt)])
        lines.append("")
    lines.extend(["## 使用边界", ""] + ["- " + _md(item) for item in report.limitations])
    return "\n".join(lines) + "\n"
