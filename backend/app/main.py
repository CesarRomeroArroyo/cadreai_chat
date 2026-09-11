from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response as StarletteResponse

from app.api.chat import error_response
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.knowledge import router as knowledge_router
from app.core.admin_auth import LoginRateLimiter
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.request_ids import request_id_from_headers
from app.core.request_limits import RequestBodyLimitMiddleware
from app.core.settings import Settings, get_settings
from app.generation.factory import create_generation_provider
from app.generation.provider import GenerationProvider
from app.generation.service import GroundedChatService
from app.rag.factory import create_knowledge_service, create_retrieval_service
from app.rag.retrieval import RetrievalService
from app.rag.service import KnowledgeService


def create_app(
    settings: Settings | None = None,
    knowledge_service: KnowledgeService | None = None,
    retrieval_service: RetrievalService | None = None,
    generation_provider: GenerationProvider | None = None,
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
        if app.state.generation_provider is None and app_settings.app_environment != "test":
            app.state.generation_provider = create_generation_provider(app_settings)
        if app.state.chat_service is None and app.state.retrieval_service is not None:
            app.state.chat_service = GroundedChatService(
                retrieval_service=app.state.retrieval_service,
                provider=app.state.generation_provider,
                min_score=app_settings.chat_retrieval_min_score,
                context_token_budget=app_settings.chat_context_token_budget,
            )
        try:
            yield
        finally:
            if app.state.generation_provider is not None:
                await app.state.generation_provider.aclose()

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
    app.state.generation_provider = generation_provider
    app.state.chat_service = None
    if app.state.retrieval_service is not None:
        app.state.chat_service = GroundedChatService(
            retrieval_service=app.state.retrieval_service,
            provider=generation_provider,
            min_score=app_settings.chat_retrieval_min_score,
            context_token_budget=app_settings.chat_context_token_budget,
        )
    app.state.knowledge_login_limiter = LoginRateLimiter(
        max_attempts=app_settings.knowledge_login_attempts,
        window_seconds=app_settings.knowledge_login_window_seconds,
    )
    app.state.chat_rate_limiter = SlidingWindowRateLimiter(
        limit=app_settings.chat_rate_limit_requests,
        window_seconds=app_settings.chat_rate_limit_window_seconds,
    )
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_bytes=app_settings.chat_max_request_bytes,
        path_prefix="/api/v1/chat",
        error_code="request_too_large",
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
    app.include_router(chat_router)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> StarletteResponse:
        if request.url.path != "/api/v1/chat":
            return await request_validation_exception_handler(request, exc)
        request_id = request_id_from_headers(request.headers)
        return error_response(
            request_id=request_id,
            status_code=422,
            code="invalid_request",
            message="Chat request is invalid.",
        )

    return app


app = create_app()
