from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.request_ids import request_id_from_headers


class RequestBodyLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        max_bytes: int,
        path_prefix: str,
        error_code: str | None = None,
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.path_prefix = path_prefix
        self.error_code = error_code

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or not str(scope.get("path", "")).startswith(self.path_prefix)
            or scope.get("method") not in {"POST", "PUT", "PATCH"}
        ):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                await self._error_response(
                    scope,
                    receive,
                    send,
                    status_code=400,
                    message="Invalid Content-Length",
                )
                return

        received = 0
        too_large = False

        async def limited_receive() -> Message:
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    too_large = True
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            if not too_large:
                await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except Exception:
            if not too_large:
                raise
        if too_large:
            await self._reject(scope, receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._error_response(
            scope,
            receive,
            send,
            status_code=413,
            message="Request body exceeds the configured size limit",
        )

    async def _error_response(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        status_code: int,
        message: str,
    ) -> None:
        content: dict[str, object]
        if self.error_code is None:
            content = {"detail": message}
            headers = None
        else:
            raw_headers = {
                key.decode("latin-1").casefold(): value.decode("latin-1")
                for key, value in scope.get("headers", [])
            }
            request_id = request_id_from_headers(raw_headers)
            content = {
                "error": {
                    "code": self.error_code,
                    "message": message,
                    "request_id": request_id,
                }
            }
            headers = {"X-Request-ID": request_id}
        response = JSONResponse(status_code=status_code, content=content, headers=headers)
        await response(scope, receive, send)
