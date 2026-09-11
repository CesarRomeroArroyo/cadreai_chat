from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from pydantic import SecretStr

from app.core.settings import Settings
from app.main import create_app
from app.rag.models import PreparedSource
from app.rag.service import KnowledgeService
from app.rag.store import SnapshotStore
from tests.rag.fakes import FakeEmbedder

ORIGIN = "https://admin.test"
PASSWORD = "correct horse battery staple"
SESSION_SECRET = "s" * 40


def make_app(tmp_path: Path, **overrides: object) -> tuple[FastAPI, KnowledgeService]:
    settings = Settings(
        app_environment="test",
        app_cors_origins=[ORIGIN],
        knowledge_admin_password=SecretStr(PASSWORD),
        knowledge_session_secret=SecretStr(SESSION_SECRET),
        knowledge_cookie_secure=True,
    ).model_copy(update=overrides)
    service = KnowledgeService(
        store=SnapshotStore(tmp_path / "index"),
        embedder=FakeEmbedder(),
        chunk_tokens=8,
        chunk_overlap=2,
    )
    return create_app(settings, service), service


async def login(client: AsyncClient) -> Response:
    response = await client.post(
        "/api/v1/knowledge/login",
        headers={"Origin": ORIGIN},
        json={"password": PASSWORD},
    )
    assert response.status_code == 200
    return response


@pytest.mark.anyio
async def test_requires_origin_and_authentication(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        assert (await client.get("/api/v1/knowledge/sources")).status_code == 401
        no_origin = await client.post("/api/v1/knowledge/login", json={"password": PASSWORD})
        wrong_origin = await client.post(
            "/api/v1/knowledge/login",
            headers={"Origin": "https://evil.example"},
            json={"password": PASSWORD},
        )
        login_response = await login(client)
        session = await client.get("/api/v1/knowledge/session")

    assert no_origin.status_code == 403
    assert wrong_origin.status_code == 403
    assert session.status_code == 200
    set_cookie = login_response.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=strict" in set_cookie
    assert "Path=/api/v1/knowledge" in set_cookie
    cookie = session.request.headers.get("cookie", "")
    assert "cadre_knowledge_session=" in cookie


@pytest.mark.anyio
async def test_login_rate_limit_is_bounded_per_client(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path, knowledge_login_attempts=2)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        responses = [
            await client.post(
                "/api/v1/knowledge/login",
                headers={"Origin": ORIGIN},
                json={"password": "wrong password"},
            )
            for _ in range(3)
        ]

    assert [response.status_code for response in responses] == [401, 401, 429]


@pytest.mark.anyio
async def test_unconfigured_authentication_fails_closed(tmp_path: Path) -> None:
    app, _ = make_app(
        tmp_path,
        knowledge_admin_password=None,
        knowledge_session_secret=None,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        login_response = await client.post(
            "/api/v1/knowledge/login",
            headers={"Origin": ORIGIN},
            json={"password": PASSWORD},
        )
        sources = await client.get("/api/v1/knowledge/sources")

    assert login_response.status_code == 503
    assert sources.status_code == 503


@pytest.mark.anyio
async def test_multi_file_ingestion_reports_each_result(tmp_path: Path) -> None:
    app, service = make_app(tmp_path)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        await login(client)
        response = await client.post(
            "/api/v1/knowledge/files",
            headers={"Origin": ORIGIN},
            data={"approved": "true"},
            files=[
                ("files", ("empty.txt", b"  ", "text/plain")),
                ("files", ("services.txt", b"AI strategy and delivery", "text/plain")),
            ],
        )
        sources = await client.get("/api/v1/knowledge/sources")

    assert response.status_code == 200
    assert [item["status"] for item in response.json()["results"]] == ["error", "indexed"]
    assert sources.status_code == 200
    assert len(sources.json()) == 1
    assert len(service.list_sources()) == 1


@pytest.mark.anyio
async def test_upload_limits_are_enforced_without_index_mutation(tmp_path: Path) -> None:
    app, service = make_app(tmp_path, knowledge_max_file_bytes=3)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        await login(client)
        response = await client.post(
            "/api/v1/knowledge/files",
            headers={"Origin": ORIGIN},
            data={"approved": "true"},
            files={"files": ("large.txt", b"four", "text/plain")},
        )

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "error"
    assert service.list_sources() == []


@pytest.mark.anyio
async def test_request_body_limit_rejects_before_ingestion(tmp_path: Path) -> None:
    app, service = make_app(tmp_path, knowledge_max_request_bytes=500)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        await login(client)
        response = await client.post(
            "/api/v1/knowledge/files",
            headers={"Origin": ORIGIN},
            data={"approved": "true"},
            files={"files": ("large.txt", b"x" * 1_000, "text/plain")},
        )

    assert response.status_code == 413
    assert service.list_sources() == []


@pytest.mark.anyio
async def test_request_body_limit_counts_streamed_chunks(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path, knowledge_max_request_bytes=500)

    async def oversized_body() -> AsyncIterator[bytes]:
        yield b'{"approved":true,"sources":["'
        yield b"x" * 600
        yield b'"]}'

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        await login(client)
        response = await client.post(
            "/api/v1/knowledge/urls",
            headers={"Origin": ORIGIN, "Content-Type": "application/json"},
            content=oversized_body(),
        )

    assert response.status_code == 413


@pytest.mark.anyio
async def test_file_count_aggregate_limit_and_approval_are_enforced(tmp_path: Path) -> None:
    app, service = make_app(tmp_path, knowledge_max_files=2, knowledge_max_upload_bytes=5)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        await login(client)
        no_approval = await client.post(
            "/api/v1/knowledge/files",
            headers={"Origin": ORIGIN},
            data={"approved": "false"},
            files={"files": ("one.txt", b"one", "text/plain")},
        )
        aggregate = await client.post(
            "/api/v1/knowledge/files",
            headers={"Origin": ORIGIN},
            data={"approved": "true"},
            files=[
                ("files", ("one.txt", b"one", "text/plain")),
                ("files", ("two.txt", b"two", "text/plain")),
            ],
        )
        too_many = await client.post(
            "/api/v1/knowledge/files",
            headers={"Origin": ORIGIN},
            data={"approved": "true"},
            files=[
                ("files", ("a.txt", b"a", "text/plain")),
                ("files", ("b.txt", b"b", "text/plain")),
                ("files", ("c.txt", b"c", "text/plain")),
            ],
        )

    assert no_approval.status_code == 422
    assert [item["status"] for item in aggregate.json()["results"]] == ["indexed", "error"]
    assert too_many.status_code == 422
    assert len(service.list_sources()) == 1


@pytest.mark.anyio
async def test_url_policy_error_is_reported_without_network_request(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        await login(client)
        response = await client.post(
            "/api/v1/knowledge/urls",
            headers={"Origin": ORIGIN},
            json={
                "approved": True,
                "sources": [{"url": "https://evil.example/private"}],
            },
        )

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "error"
    assert "allowed Cadre AI domain" in response.json()["results"][0]["detail"]


@pytest.mark.anyio
async def test_invalid_custom_url_source_id_is_reported(tmp_path: Path) -> None:
    app, service = make_app(tmp_path)

    def fake_prepare_url(*_args: object, **_kwargs: object) -> PreparedSource:
        return service.prepare_file(
            filename="source.txt", content_type="text/plain", data=b"approved source"
        )

    service.prepare_url = fake_prepare_url  # type: ignore[method-assign,assignment]
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        await login(client)
        response = await client.post(
            "/api/v1/knowledge/urls",
            headers={"Origin": ORIGIN},
            json={
                "approved": True,
                "sources": [{"url": "https://cadreai.com/source", "source_id": "../../unsafe"}],
            },
        )

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "error"
    assert service.list_sources() == []


@pytest.mark.anyio
async def test_delete_rebuild_and_logout_flow(tmp_path: Path) -> None:
    app, service = make_app(tmp_path)
    prepared = service.prepare_file(
        filename="source.txt", content_type="text/plain", data=b"approved source"
    )
    source_id = service.upsert([prepared])[0].source_id
    assert source_id is not None

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        await login(client)
        rebuild = await client.post("/api/v1/knowledge/rebuild", headers={"Origin": ORIGIN})
        removed = await client.delete(
            f"/api/v1/knowledge/sources/{source_id}", headers={"Origin": ORIGIN}
        )
        logout = await client.post("/api/v1/knowledge/logout", headers={"Origin": ORIGIN})
        after_logout = await client.get("/api/v1/knowledge/sources")

    assert rebuild.status_code == 200
    assert rebuild.json()["chunk_count"] == 1
    assert removed.status_code == 200
    assert logout.status_code == 204
    assert after_logout.status_code == 401
