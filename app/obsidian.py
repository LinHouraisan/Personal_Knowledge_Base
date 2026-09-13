import os
import webbrowser
from pathlib import PurePosixPath
from urllib.parse import quote, urlencode


def build_obsidian_uri(vault_name: str, relative_path: str) -> str:
    normalized = relative_path.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not vault_name.strip() or path.is_absolute() or ".." in path.parts:
        raise ValueError("Obsidian 路径必须位于指定 Vault 内")
    query = urlencode(
        {"vault": vault_name.strip(), "file": path.as_posix()},
        quote_via=quote,
    )
    return f"obsidian://open?{query}"


def open_obsidian_uri(uri: str) -> None:
    if not uri.startswith("obsidian://open?"):
        raise ValueError("只允许打开 Obsidian 笔记 URI")
    if os.name == "nt":
        os.startfile(uri)  # type: ignore[attr-defined]
        return
    webbrowser.open(uri)

