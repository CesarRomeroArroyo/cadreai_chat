import socket

import httpx
import pytest

from app.rag.errors import DownloadError, UnsafeUrlError
from app.rag.url_fetcher import fetch_url, validate_url


@pytest.fixture(autouse=True)
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )


def test_validates_https_allowlist_and_rejects_unsafe_urls() -> None:
    assert (
        validate_url("https://www.cadreai.com/services#details", ["cadreai.com"])
        == "https://www.cadreai.com/services"
    )
    with pytest.raises(UnsafeUrlError):
        validate_url("http://cadreai.com", ["cadreai.com"])
    with pytest.raises(UnsafeUrlError):
        validate_url("https://cadreai.com:8443", ["cadreai.com"])
    with pytest.raises(UnsafeUrlError):
        validate_url("https://cadreai.com.evil.example", ["cadreai.com"])


def test_rejects_private_dns_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    )

    with pytest.raises(UnsafeUrlError, match="non-public"):
        validate_url("https://cadreai.com", ["cadreai.com"])


def test_fetches_bounded_content_and_revalidates_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(
            200,
            headers={"content-type": "text/html", "content-length": "13"},
            content=b"<p>Cadre</p>",
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        url, content_type, data = fetch_url(
            "https://cadreai.com/start",
            allowed_hosts=["cadreai.com"],
            max_bytes=100,
            timeout_seconds=1,
            client=client,
        )

    assert url == "https://cadreai.com/final"
    assert content_type == "text/html"
    assert data == b"<p>Cadre</p>"


def test_rejects_oversized_response() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            headers={"content-type": "text/plain", "content-length": "101"},
            content=b"x" * 101,
        )
    )
    with (
        httpx.Client(transport=transport) as client,
        pytest.raises(DownloadError, match="size limit"),
    ):
        fetch_url(
            "https://cadreai.com/large",
            allowed_hosts=["cadreai.com"],
            max_bytes=100,
            timeout_seconds=1,
            client=client,
        )
