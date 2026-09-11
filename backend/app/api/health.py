from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: Literal["ready"]
    source_count: int
    chunk_count: int


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadinessResponse)
def ready(request: Request) -> ReadinessResponse:
    retrieval_service = request.app.state.retrieval_service
    if retrieval_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge index is not ready",
        )
    readiness = retrieval_service.readiness()
    if not readiness.ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge index is not ready",
        )
    return ReadinessResponse(
        status="ready",
        source_count=readiness.source_count,
        chunk_count=readiness.chunk_count,
    )
