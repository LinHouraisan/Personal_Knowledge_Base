from app.cli import main
from app.obsidian import build_obsidian_uri


def test_uri_encodes_chinese_spaces_and_nested_path():
    uri = build_obsidian_uri("我的 知识库", "项目/RAG 方案.md")

    assert uri == (
        "obsidian://open?"
        "vault=%E6%88%91%E7%9A%84%20%E7%9F%A5%E8%AF%86%E5%BA%93&"
        "file=%E9%A1%B9%E7%9B%AE%2FRAG%20%E6%96%B9%E6%A1%88.md"
    )


def test_cli_opens_only_a_generated_obsidian_uri(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr("app.cli.open_obsidian_uri", opened.append)

    result = main(
        ["open", "--vault", "我的知识库", "--file", "项目/RAG 方案.md"]
    )

    assert result == 0
    assert opened == [build_obsidian_uri("我的知识库", "项目/RAG 方案.md")]

