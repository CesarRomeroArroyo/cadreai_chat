from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from app.api.health import router as health_router
from app.api.knowledge import router as knowledge_router
from app.core.admin_auth import LoginRateLimiter
from app.core.request_limits import RequestBodyLimitMiddleware
from app.core.settings import Settings, get_settings
from app.rag.factory import create_knowledge_service, create_retrieval_service
from app.rag.retrieval import RetrievalService
from app.rag.service import KnowledgeService


def create_app(
    settings: Settings | None = None,
    knowledge_service: KnowledgeService | None = None,
    retrieval_service: RetrievalService | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if app.state.knowledge_service is None and app_settings.app_environment != "test":
            app.state.knowledge_service = await run_in_threadpool(
                create_knowledge_service, app_settings
            )
        if app.state.retrieval_service is None and app.state.knowledge_service is not None:
            app.state.retrieval_service = await run_in_threadpool(
                create_retrieval_service,
                app_settings,
                app.state.knowledge_service,
            )
        yield

    app = FastAPI(
        title="Cadre AI Support API",
        version="0.1.0",
        docs_url="/docs" if app_settings.app_environment == "development" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.knowledge_service = knowledge_service
    app.state.retrieval_service = retrieval_service
    if app.state.retrieval_service is None and knowledge_service is not None:
        app.state.retrieval_service = create_retrieval_service(app_settings, knowledge_service)
    app.state.knowledge_login_limiter = LoginRateLimiter(
        max_attempts=app_settings.knowledge_login_attempts,
        window_seconds=app_settings.knowledge_login_window_seconds,
    )
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_bytes=app_settings.knowledge_max_request_bytes,
        path_prefix="/api/v1/knowledge",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.app_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )
    app.include_router(health_router)
    app.include_router(knowledge_router)
    return app


app = create_app()
