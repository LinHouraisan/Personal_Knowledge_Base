import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel, Field

from app.agent import KnowledgeAgent, build_knowledge_agent
from app.config import Settings, get_settings
from app.index import JsonVectorIndex
from app.knowledge import KnowledgeService


logger = logging.getLogger("obsidian_knowledge")


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


def create_app(
    settings: Settings | None = None,
    service: KnowledgeService | None = None,
    agent: KnowledgeAgent | None = None,
) -> FastAPI:
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        knowledge = service
        if knowledge is None:
            embedder = OpenAIEmbeddings(
                model=resolved.embedding_model,
                base_url=resolved.embedding_base_url,
                api_key=(
                    resolved.embedding_api_key.get_secret_value()
                    if resolved.embedding_api_key
                    else "not-configured"
                ),
                check_embedding_ctx_length=False,
            )
            index = JsonVectorIndex(
                resolved.vault_path,
                resolved.index_path,
                embedder,
            )
            knowledge = KnowledgeService(
                resolved.vault_path,
                resolved.vault_name,
                index,
            )
        await knowledge.load()
        application.state.knowledge = knowledge
        application.state.agent = agent or build_knowledge_agent(resolved, knowledge)
        application.state.chat_requires_key = (
            agent is None
            and resolved.chat_api_key is None
            and "127.0.0.1" not in resolved.chat_base_url
            and "localhost" not in resolved.chat_base_url
        )
        yield

    application = FastAPI(
        title="Obsidian 个人知识库 RAG",
        version="0.1.0",
        lifespan=lifespan,
    )

    @application.middleware("http")
    async def request_log(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        logger.info(
            "method=%s path=%s status=%s latency_ms=%s",
            request.method,
            request.url.path,
            response.status_code,
            int((time.perf_counter() - started) * 1000),
        )
        return response

    @application.get("/health")
    async def health():
        status = application.state.knowledge.status()
        return {
            "status": "ok" if status.index_ready else "degraded",
            **status.model_dump(),
        }

    @application.post("/v1/index/rebuild")
    async def rebuild_index():
        try:
            return await application.state.knowledge.rebuild()
        except Exception:
            raise HTTPException(status_code=503, detail="索引重建失败，请检查 Embedding 服务") from None

    @application.get("/v1/search")
    async def search(
        q: str = Query(min_length=1, max_length=2000),
        top_k: int = Query(default=3, ge=1, le=20),
    ):
        try:
            sources = await application.state.knowledge.search(q, top_k)
        except Exception:
            raise HTTPException(status_code=503, detail="检索服务暂时不可用") from None
        logger.info("event=search source_count=%s", len(sources))
        return {"sources": [source.model_dump() for source in sources]}

    @application.post("/v1/chat")
    async def chat(request: ChatRequest):
        if application.state.chat_requires_key:
            raise HTTPException(status_code=503, detail="聊天模型尚未配置")
        try:
            result = await application.state.agent.answer(request.question)
        except Exception:
            raise HTTPException(status_code=503, detail="聊天模型暂时不可用") from None
        logger.info("event=chat source_count=%s status=%s", len(result.sources), result.status)
        return result

    @application.get("/v1/notes/{note_id}")
    async def read_note(note_id: str):
        try:
            return application.state.knowledge.read_by_id(note_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="笔记不存在") from None

    @application.get("/", include_in_schema=False)
    async def home():
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    return application


app = create_app()

