import json
import logging
import time
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from app.core.request_ids import request_id_from_headers
from app.generation.errors import (
    InsufficientFundsError,
    InvalidCredentialsError,
    InvalidProviderRequestError,
    MalformedProviderResponseError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.generation.service import GroundedChatService, HistoryTurn

router = APIRouter(prefix="/api/v1", tags=["chat"])
logger = logging.getLogger("cadre.chat")
logger.setLevel(logging.INFO)


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=10_000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=20)


class ChatSource(BaseModel):
    source_id: str
    title: str
    url: str | None
    locations: list[str]


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]
    abstained: bool
    request_id: str


def error_response(*, request_id: str, status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        headers={"X-Request-ID": request_id},
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
            }
        },
    )


def _log_result(
    *,
    request_id: str,
    status_code: int,
    started: float,
    retrieval_count: int = 0,
    provider_latency_ms: int | None = None,
    error_category: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> None:
    logger.info(
        json.dumps(
            {
                "event": "chat_request",
                "request_id": request_id,
                "route": "/api/v1/chat",
                "status": status_code,
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "retrieval_count": retrieval_count,
                "provider_latency_ms": provider_latency_ms,
                "error_category": error_category,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
            separators=(",", ":"),
        )
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest, request: Request, response: Response
) -> ChatResponse | JSONResponse:
    started = time.perf_counter()
    request_id = request_id_from_headers(request.headers)
    settings = request.app.state.settings
    client_key = request.client.host if request.client else "unknown"
    if not request.app.state.chat_rate_limiter.consume(client_key):
        _log_result(
            request_id=request_id,
            status_code=429,
            started=started,
            error_category="rate_limit",
        )
        return error_response(
            request_id=request_id,
            status_code=429,
            code="rate_limited",
            message="Too many requests; try again later.",
        )

    message = payload.message.strip()
    history = [
        HistoryTurn(role=item.role, content=item.content.strip()) for item in payload.history
    ]
    history_chars = sum(len(item.content) for item in history)
    invalid = (
        not message
        or len(message) > settings.chat_max_input_chars
        or len(history) > settings.chat_max_history_messages
        or any(
            not item.content or len(item.content) > settings.chat_max_input_chars
            for item in history
        )
        or history_chars > settings.chat_max_history_chars
    )
    if invalid:
        _log_result(
            request_id=request_id,
            status_code=422,
            started=started,
            error_category="invalid_request",
        )
        return error_response(
            request_id=request_id,
            status_code=422,
            code="invalid_request",
            message="Message or conversation history exceeds allowed limits.",
        )

    service: GroundedChatService | None = request.app.state.chat_service
    if service is None or not service.retrieval_service.readiness().ready:
        _log_result(
            request_id=request_id,
            status_code=503,
            started=started,
            error_category="not_ready",
        )
        return error_response(
            request_id=request_id,
            status_code=503,
            code="not_ready",
            message="Verified knowledge is not ready yet.",
        )

    try:
        outcome = await service.answer(message, history)
    except ProviderRateLimitError:
        status_code, code, safe_message = 503, "provider_busy", "Answer service is busy."
    except ProviderTimeoutError:
        status_code, code, safe_message = 504, "provider_timeout", "Answer service timed out."
    except (InvalidCredentialsError, InsufficientFundsError):
        status_code, code, safe_message = (
            503,
            "provider_unavailable",
            "Answer service is unavailable.",
        )
    except (ProviderUnavailableError, InvalidProviderRequestError):
        status_code, code, safe_message = (
            503,
            "provider_unavailable",
            "Answer service is unavailable.",
        )
    except MalformedProviderResponseError:
        status_code, code, safe_message = (
            502,
            "provider_response_invalid",
            "Answer service returned an invalid response.",
        )
    except Exception:
        logger.exception(
            "Unexpected chat failure",
            extra={"request_id": request_id, "route": "/api/v1/chat"},
        )
        status_code, code, safe_message = 500, "internal_error", "Request could not be completed."
    else:
        usage = outcome.usage
        _log_result(
            request_id=request_id,
            status_code=200,
            started=started,
            retrieval_count=outcome.retrieval_count,
            provider_latency_ms=outcome.provider_latency_ms,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
        )
        response.headers["X-Request-ID"] = request_id
        return ChatResponse(
            answer=outcome.answer,
            sources=[
                ChatSource(
                    source_id=source.source_id,
                    title=source.title,
                    url=source.url,
                    locations=list(source.locations),
                )
                for source in outcome.sources
            ],
            abstained=outcome.abstained,
            request_id=request_id,
        )

    _log_result(
        request_id=request_id,
        status_code=status_code,
        started=started,
        error_category=code,
    )
    return error_response(
        request_id=request_id,
        status_code=status_code,
        code=code,
        message=safe_message,
    )
