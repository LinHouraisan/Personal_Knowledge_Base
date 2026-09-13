from pathlib import Path

import pytest


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    (root / "项目").mkdir(parents=True)
    (root / "技术").mkdir()
    (root / ".obsidian").mkdir()
    (root / "attachments").mkdir()

    (root / "项目" / "RAG 方案.md").write_text(
        """---
status: active
tags:
  - AI
  - RAG
aliases:
  - 检索方案
---
# RAG 方案

这份方案用于个人知识库的语义检索。 #AI #RAG

## 关联决策

向量模型见 [[Embedding 选择]]，项目结论见 [[项目复盘]]。
""",
        encoding="utf-8",
    )
    (root / "技术" / "Embedding 选择.md").write_text(
        "# Embedding 选择\n\n本地使用 bge-m3。\n",
        encoding="utf-8",
    )
    (root / "项目复盘.md").write_text(
        "# 项目复盘\n\n索引应当支持增量更新。\n",
        encoding="utf-8",
    )
    (root / ".obsidian" / "隐藏.md").write_text("不应扫描", encoding="utf-8")
    (root / "attachments" / "readme.md").write_text("不应扫描", encoding="utf-8")
    return root

