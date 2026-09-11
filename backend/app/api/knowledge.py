from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.core.admin_auth import (
    LoginRateLimiter,
    clear_session_cookie,
    create_session_token,
    require_admin_session,
    require_allowed_origin,
    require_auth_settings,
    set_session_cookie,
    verify_password,
)
from app.core.settings import Settings
from app.rag.errors import IngestionError
from app.rag.models import IngestionResult, IngestionStatus, PreparedSource, SourceRecord
from app.rag.service import KnowledgeService, validate_source_id

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


class SessionResponse(BaseModel):
    authenticated: Literal[True] = True


class UrlSourceInput(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    source_id: str | None = Field(default=None, min_length=1, max_length=128)
    title: str | None = Field(default=None, min_length=1, max_length=300)


class UrlBatchRequest(BaseModel):
    approved: Literal[True]
    sources: list[UrlSourceInput]


class IngestionResponse(BaseModel):
    results: list[IngestionResult]


class RebuildResponse(BaseModel):
    chunk_count: int


class DeleteResponse(BaseModel):
    removed: Literal[True] = True


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _service(request: Request) -> KnowledgeService:
    service: KnowledgeService | None = request.app.state.knowledge_service
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge service is not ready",
        )
    return service


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _authenticate(request: Request) -> Settings:
    settings = _settings(request)
    require_admin_session(request, settings)
    return settings


async def _upsert_sources(
    service: KnowledgeService, prepared: list[PreparedSource]
) -> list[IngestionResult]:
    try:
        return await run_in_threadpool(service.upsert, prepared)
    except IngestionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


async def _read_upload(file: UploadFile, *, file_limit: int, remaining: int) -> bytes:
    parts: list[bytes] = []
    total = 0
    try:
        while chunk := await file.read(64 * 1024):
            total += len(chunk)
            if total > file_limit:
                raise IngestionError("File exceeds the individual size limit")
            if total > remaining:
                raise IngestionError("Upload exceeds the aggregate size limit")
            parts.append(chunk)
    finally:
        await file.close()
    return b"".join(parts)


@router.post("/login", response_model=SessionResponse)
def login(payload: LoginRequest, request: Request, response: Response) -> SessionResponse:
    settings = _settings(request)
    require_allowed_origin(request, settings)
    password, secret = require_auth_settings(settings)
    limiter: LoginRateLimiter = request.app.state.knowledge_login_limiter
    client_key = _client_key(request)
    limiter.check(client_key)
    if not verify_password(payload.password, password):
        limiter.record_failure(client_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid administrator credentials",
        )
    limiter.clear(client_key)
    token = create_session_token(secret=secret, ttl_seconds=settings.knowledge_session_ttl_seconds)
    set_session_cookie(response, settings, token)
    return SessionResponse()


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response) -> None:
    settings = _authenticate(request)
    require_allowed_origin(request, settings)
    clear_session_cookie(response, settings)


@router.get("/session", response_model=SessionResponse)
def session(request: Request) -> SessionResponse:
    _authenticate(request)
    return SessionResponse()


@router.get("/sources", response_model=list[SourceRecord])
def list_sources(request: Request) -> list[SourceRecord]:
    _authenticate(request)
    return _service(request).list_sources()


@router.post("/files", response_model=IngestionResponse)
async def add_files(
    request: Request,
    approved: Annotated[bool, Form()],
    files: Annotated[list[UploadFile], File()],
) -> IngestionResponse:
    settings = _authenticate(request)
    require_allowed_origin(request, settings)
    if not approved:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Official-source approval confirmation is required",
        )
    service = _service(request)
    if not files or len(files) > settings.knowledge_max_files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Upload must contain 1-{settings.knowledge_max_files} files",
        )

    prepared: list[PreparedSource] = []
    prepared_indices: list[int] = []
    ordered_results: list[IngestionResult | None] = [None] * len(files)
    seen_ids: set[str] = set()
    aggregate_size = 0
    for index, file in enumerate(files):
        name = file.filename or "unnamed"
        try:
            data = await _read_upload(
                file,
                file_limit=settings.knowledge_max_file_bytes,
                remaining=settings.knowledge_max_upload_bytes - aggregate_size,
            )
            aggregate_size += len(data)
            source = await run_in_threadpool(
                service.prepare_file,
                filename=name,
                content_type=file.content_type,
                data=data,
            )
            if source.source_id in seen_ids:
                raise IngestionError("Upload contains duplicate source filenames")
            seen_ids.add(source.source_id)
            prepared.append(source)
            prepared_indices.append(index)
        except (IngestionError, OSError) as exc:
            ordered_results[index] = IngestionResult(
                source_id=None,
                name=name,
                status=IngestionStatus.ERROR,
                detail=str(exc),
            )
    if prepared:
        indexed_results = await _upsert_sources(service, prepared)
        for index, result in zip(prepared_indices, indexed_results, strict=True):
            ordered_results[index] = result
    return IngestionResponse(results=[result for result in ordered_results if result is not None])


@router.post("/urls", response_model=IngestionResponse)
async def add_urls(payload: UrlBatchRequest, request: Request) -> IngestionResponse:
    settings = _authenticate(request)
    require_allowed_origin(request, settings)
    service = _service(request)
    if not payload.sources or len(payload.sources) > settings.knowledge_max_urls:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Request must contain 1-{settings.knowledge_max_urls} URLs",
        )

    prepared: list[PreparedSource] = []
    prepared_indices: list[int] = []
    ordered_results: list[IngestionResult | None] = [None] * len(payload.sources)
    seen_ids: set[str] = set()
    for index, item in enumerate(payload.sources):
        try:
            source = await run_in_threadpool(
                service.prepare_url,
                item.url,
                allowed_hosts=tuple(settings.knowledge_allowed_hosts),
                max_bytes=settings.knowledge_max_url_bytes,
                timeout_seconds=settings.knowledge_url_timeout_seconds,
            )
            source = PreparedSource(
                source_id=item.source_id or source.source_id,
                kind=source.kind,
                title=item.title or source.title,
                locator=source.locator,
                retrieved_at=source.retrieved_at,
                sections=source.sections,
            )
            validate_source_id(source.source_id)
            if source.source_id in seen_ids:
                raise IngestionError("Request contains duplicate source IDs")
            seen_ids.add(source.source_id)
            prepared.append(source)
            prepared_indices.append(index)
        except (IngestionError, OSError) as exc:
            ordered_results[index] = IngestionResult(
                source_id=item.source_id,
                name=item.title or item.url,
                status=IngestionStatus.ERROR,
                detail=str(exc),
            )
    if prepared:
        indexed_results = await _upsert_sources(service, prepared)
        for index, result in zip(prepared_indices, indexed_results, strict=True):
            ordered_results[index] = result
    return IngestionResponse(results=[result for result in ordered_results if result is not None])


@router.delete("/sources/{source_id}", response_model=DeleteResponse)
async def delete_source(source_id: str, request: Request) -> DeleteResponse:
    settings = _authenticate(request)
    require_allowed_origin(request, settings)
    try:
        removed = await run_in_threadpool(_service(request).remove, source_id)
    except IngestionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return DeleteResponse()


@router.post("/rebuild", response_model=RebuildResponse)
async def rebuild(request: Request) -> RebuildResponse:
    settings = _authenticate(request)
    require_allowed_origin(request, settings)
    try:
        chunk_count = await run_in_threadpool(_service(request).rebuild)
    except IngestionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return RebuildResponse(chunk_count=chunk_count)
