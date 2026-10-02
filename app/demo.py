import argparse
from pathlib import Path

import uvicorn

from app.config import Settings
from app.deepseek import DeepSeekAssistant
from app.knowledge import KnowledgeService
from app.lexical import LexicalRetriever
from app.main import create_app
from app.models import AgentAnswer


class ExtractiveDemoAgent:
    def __init__(self, service: KnowledgeService):
        self.service = service

    async def answer(self, question: str) -> AgentAnswer:
        sources = await self.service.search(question, 3)
        text = "离线证据摘录，未调用生成模型。\n\n"
        text += "\n\n".join(f"[{i}] {source.excerpt}" for i, source in enumerate(sources, 1)) if sources else "当前公开样例中未找到相关证据。"
        return AgentAnswer(status="answered" if sources else "no_evidence", answer=text, sources=sources)


def create_demo_app(*, ai=None):
    root = Path(__file__).resolve().parents[1]
    settings = Settings(
        _env_file=None, vault_path=root / "sample_vault", vault_name="公开虚构演示知识库",
        index_path=root / ".codex_artifacts" / "unused-demo-index.json",
        planner_enabled=False, retrieval_mode="vector",
    )
    service = KnowledgeService(settings.vault_path, settings.vault_name, LexicalRetriever(settings.vault_path))
    return create_app(settings, service, ExtractiveDemoAgent(service), demo_mode=True, ai=ai)


def main():
    parser = argparse.ArgumentParser(description="公开虚构资料的离线词法/摘录演示，不调用生成模型")
    parser.add_argument("--port", type=int, default=8011)
    parser.add_argument("--ai", action="store_true", help="允许在本机页面配置 DeepSeek；仍只读取公开虚构笔记")
    args = parser.parse_args()
    ai = DeepSeekAssistant(Path(__file__).resolve().parents[1] / ".env") if args.ai else None
    uvicorn.run(create_demo_app(ai=ai), host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
