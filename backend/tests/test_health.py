import pytest
from httpx import ASGITransport, AsyncClient

from app.core.settings import Settings
from app.main import create_app


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
