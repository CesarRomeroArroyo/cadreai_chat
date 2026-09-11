import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException, Request, Response, status

from app.core.settings import Settings

AUTH_UNAVAILABLE = "Knowledge administration is not configured"
AUTH_REQUIRED = "Administrator authentication required"


class LoginRateLimiter:
    def __init__(
        self,
        *,
        max_attempts: int,
        window_seconds: int,
        max_tracked_clients: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.max_tracked_clients = max_tracked_clients
        self.clock = clock
        self._attempts: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = self.clock()
        with self._lock:
            attempts = self._attempts.get(key)
            if attempts is None:
                return
            while attempts and attempts[0] <= now - self.window_seconds:
                attempts.popleft()
            if len(attempts) >= self.max_attempts:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many login attempts; try again later",
                )

    def record_failure(self, key: str) -> None:
        with self._lock:
            attempts = self._attempts.get(key)
            if attempts is None:
                if len(self._attempts) >= self.max_tracked_clients:
                    self._attempts.pop(next(iter(self._attempts)))
                attempts = deque()
                self._attempts[key] = attempts
            attempts.append(self.clock())

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


def require_auth_settings(settings: Settings) -> tuple[str, str]:
    password = settings.knowledge_admin_password
    session_secret = settings.knowledge_session_secret
    if password is None or session_secret is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=AUTH_UNAVAILABLE
        )
    password_value = password.get_secret_value()
    secret_value = session_secret.get_secret_value()
    if len(password_value) < 16 or len(secret_value) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=AUTH_UNAVAILABLE
        )
    return password_value, secret_value


def verify_password(candidate: str, configured: str) -> bool:
    return hmac.compare_digest(
        hashlib.sha256(candidate.encode()).digest(),
        hashlib.sha256(configured.encode()).digest(),
    )


def _signature(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def create_session_token(*, secret: str, ttl_seconds: int, now: int | None = None) -> str:
    issued_at = int(time.time()) if now is None else now
    payload = f"v1.{issued_at + ttl_seconds}.{secrets.token_urlsafe(18)}"
    return f"{payload}.{_signature(payload, secret)}"


def verify_session_token(token: str, *, secret: str, now: int | None = None) -> bool:
    parts = token.split(".")
    if len(parts) != 4 or parts[0] != "v1":
        return False
    payload = ".".join(parts[:3])
    if not hmac.compare_digest(parts[3], _signature(payload, secret)):
        return False
    try:
        expires_at = int(parts[1])
    except ValueError:
        return False
    current_time = int(time.time()) if now is None else now
    return current_time < expires_at


def set_session_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        key=settings.knowledge_session_cookie,
        value=token,
        max_age=settings.knowledge_session_ttl_seconds,
        httponly=True,
        secure=settings.knowledge_cookie_secure,
        samesite="strict",
        path="/api/v1/knowledge",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.knowledge_session_cookie,
        httponly=True,
        secure=settings.knowledge_cookie_secure,
        samesite="strict",
        path="/api/v1/knowledge",
    )


def require_allowed_origin(request: Request, settings: Settings) -> None:
    origin = request.headers.get("origin")
    if origin is None or origin.rstrip("/") not in {
        allowed.rstrip("/") for allowed in settings.app_cors_origins
    }:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid request origin")


def require_admin_session(request: Request, settings: Settings) -> None:
    _, secret = require_auth_settings(settings)
    token = request.cookies.get(settings.knowledge_session_cookie, "")
    if not verify_session_token(token, secret=secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTH_REQUIRED)
