import ipaddress
import socket
from collections.abc import Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from app.rag.errors import DownloadError, UnsafeUrlError

REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def _is_allowed_host(host: str, allowed_hosts: Iterable[str]) -> bool:
    normalized = host.rstrip(".").casefold()
    return any(
        normalized == allowed.rstrip(".").casefold()
        or normalized.endswith(f".{allowed.rstrip('.').casefold()}")
        for allowed in allowed_hosts
    )


def validate_url(url: str, allowed_hosts: Iterable[str]) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme.casefold() != "https":
        raise UnsafeUrlError("Only HTTPS URLs are allowed")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URL credentials are not allowed")
    if parsed.port not in {None, 443}:
        raise UnsafeUrlError("Only the default HTTPS port is allowed")
    hostname = (parsed.hostname or "").rstrip(".").casefold()
    if not hostname or not _is_allowed_host(hostname, allowed_hosts):
        raise UnsafeUrlError("URL hostname is not an allowed Cadre AI domain")

    try:
        addresses = {entry[4][0] for entry in socket.getaddrinfo(hostname, 443)}
    except socket.gaierror as exc:
        raise UnsafeUrlError("URL hostname could not be resolved") from exc
    if not addresses:
        raise UnsafeUrlError("URL hostname did not resolve")
    for address in addresses:
        if not ipaddress.ip_address(address).is_global:
            raise UnsafeUrlError("URL resolves to a non-public network address")

    normalized_netloc = hostname
    return urlunsplit(("https", normalized_netloc, parsed.path or "/", parsed.query, ""))


def fetch_url(
    url: str,
    *,
    allowed_hosts: Iterable[str],
    max_bytes: int,
    timeout_seconds: float,
    max_redirects: int = 3,
    client: httpx.Client | None = None,
) -> tuple[str, str, bytes]:
    owns_client = client is None
    http_client = client or httpx.Client(
        timeout=httpx.Timeout(timeout_seconds),
        follow_redirects=False,
        headers={"User-Agent": "CadreAIKnowledgeBot/1.0"},
    )
    current_url = validate_url(url, allowed_hosts)
    try:
        for _ in range(max_redirects + 1):
            try:
                with http_client.stream("GET", current_url) as response:
                    if response.status_code in REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        if not location:
                            raise DownloadError("Redirect response omitted its destination")
                        current_url = validate_url(urljoin(current_url, location), allowed_hosts)
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "")
                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            declared_size = int(content_length)
                        except ValueError as exc:
                            raise DownloadError("Remote document reported an invalid size") from exc
                        if declared_size > max_bytes:
                            raise DownloadError("Remote document exceeds the size limit")
                    parts: list[bytes] = []
                    total = 0
                    for part in response.iter_bytes():
                        total += len(part)
                        if total > max_bytes:
                            raise DownloadError("Remote document exceeds the size limit")
                        parts.append(part)
                    return current_url, content_type, b"".join(parts)
            except httpx.HTTPError as exc:
                raise DownloadError("Official source could not be downloaded") from exc
        raise DownloadError("URL exceeded the redirect limit")
    finally:
        if owns_client:
            http_client.close()
