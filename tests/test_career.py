import pytest
import pytest_asyncio
from pydantic import ValidationError

from app.career import CareerRequest, build_career_report, career_report_markdown
from app.knowledge import KnowledgeService
from app.lexical import LexicalRetriever


@pytest_asyncio.fixture
async def service(tmp_path):
    (tmp_path / "api.md").write_text("# 接口实践\n\n使用 FastAPI 实现只读接口。", encoding="utf-8")
    (tmp_path / "sql.md").write_text("# 汇总实践\n\n用 SQL 汇总记录。", encoding="utf-8")
    result = KnowledgeService(tmp_path, "公开测试", LexicalRetriever(tmp_path))
    await result.load()
    return result


def test_evidence_coverage_and_original_excerpt(service):
    report = build_career_report("要求 FastAPI、SQL 和 React。", service)
    by_skill = {item.skill_id: item for item in report.requirements}
    assert [r.skill_id for r in report.requirements] == ["fastapi", "sql", "react"]
    assert by_skill["fastapi"].status == by_skill["sql"].status == "evidence_found"
    assert by_skill["react"].status == "not_recorded"
    assert report.recognized_count == 3 and report.with_evidence_count == 2
    assert report.coverage_ratio == 2 / 3
    for item in report.requirements:
        for source in item.sources:
            assert source.excerpt in service.read_by_id(source.note_id).content
            assert source.chunk_id and source.heading and source.score is None
    assert "当前知识库未找到相关记录" in career_report_markdown(report)


def test_aliases_order_boundaries_and_unrecognized(service):
    report = build_career_report("React.js 与 reactjs；TS 和 TypeScript；NoSQL cats；RAG 检索增强生成", service)
    assert [r.skill_id for r in report.requirements] == ["react", "typescript", "rag"]
    assert report.requirements[0].matched_terms == ["react.js", "reactjs"]
    assert report.requirements[0].jd_excerpt == "React.js 与 reactjs；"
    empty = build_career_report("Java NoSQL cats 未识别要求", service)
    assert empty.requirements == [] and empty.coverage_ratio is None
    assert len(empty.limitations) >= 3


@pytest.mark.parametrize("value", ["   \n", "x" * 12001, 1, None])
def test_request_validation(value):
    with pytest.raises(ValidationError):
        CareerRequest(jd_text=value)
    assert CareerRequest(jd_text="  SQL  ").jd_text == "SQL"


@pytest.mark.asyncio
async def test_body_only_nfkc_excerpt_and_note_dedup(tmp_path):
    (tmp_path / "title-only.md").write_text("---\ntags: [SQL]\n---\n# SQL\n\n没有实现记录。", encoding="utf-8")
    original = "# 原文\n\n" + "㍿ " * 160 + "使用 ＳＱＬ 汇总。\n保持原文。\n\n第二处 SQL。"
    (tmp_path / "body.md").write_text(original, encoding="utf-8")
    (tmp_path / "tag-only.md").write_text("# 资料\n\n#SQL", encoding="utf-8")
    service = KnowledgeService(tmp_path, "test", LexicalRetriever(tmp_path))
    await service.load()
    sources = service.keyword_sources(["sql"])
    assert len(sources) == 1 and sources[0].relative_path == "body.md"
    assert "ＳＱＬ" in sources[0].excerpt and sources[0].excerpt in original
    assert len(sources[0].excerpt) <= 240
    assert service.keyword_sources(["nosql"]) == []


def test_markdown_escapes_untrusted_jd(service):
    markdown = career_report_markdown(build_career_report('SQL <img src=x onerror=alert(1)> [click](javascript:x)', service))
    assert "<img" not in markdown and "](javascript:" not in markdown
