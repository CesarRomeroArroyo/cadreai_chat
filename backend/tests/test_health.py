from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.settings import Settings
from app.main import create_app
from app.rag.service import KnowledgeService
from app.rag.store import SnapshotStore
from tests.rag.fakes import FakeEmbedder


@pytest.mark.anyio
async def test_health_returns_process_liveness() -> None:
    app = create_app(Settings(app_environment="test"))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_ready_requires_a_compatible_active_snapshot(tmp_path: Path) -> None:
    settings = Settings(app_environment="test")
    unavailable_app = create_app(settings)
    service = KnowledgeService(
        store=SnapshotStore(tmp_path / "index"),
        embedder=FakeEmbedder(),
        chunk_tokens=8,
        chunk_overlap=2,
    )
    service.rebuild()
    ready_app = create_app(settings, service)

    async with AsyncClient(
        transport=ASGITransport(app=unavailable_app), base_url="http://testserver"
    ) as client:
        unavailable = await client.get("/ready")
    async with AsyncClient(
        transport=ASGITransport(app=ready_app), base_url="http://testserver"
    ) as client:
        ready = await client.get("/ready")

    assert unavailable.status_code == 503
    assert unavailable.json() == {"detail": "Knowledge index is not ready"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "source_count": 0, "chunk_count": 0}
