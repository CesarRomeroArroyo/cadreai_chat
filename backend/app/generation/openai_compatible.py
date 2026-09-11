import asyncio
from collections.abc import Mapping
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from app.generation.errors import (
    InsufficientFundsError,
    InvalidCredentialsError,
    InvalidProviderRequestError,
    MalformedProviderResponseError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.generation.models import GenerationMessage, GenerationResult, TokenUsage

ProviderName = Literal["openai", "openrouter"]
EXPECTED_HOSTS: dict[ProviderName, str] = {
    "openai": "api.openai.com",
    "openrouter": "openrouter.ai",
}


def validate_provider_configuration(
    *, provider: ProviderName, base_url: str, api_key: str, model: str
) -> str:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != EXPECTED_HOSTS[provider]
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/v1"
    ):
        raise ValueError(f"Invalid {provider} base URL")
    if len(api_key) < 8:
        raise ValueError("Chat API key is not configured")
    if not model.strip() or len(model) > 200 or any(ord(character) < 32 for character in model):
        raise ValueError("Chat model is not configured")
    return f"{base_url.rstrip('/')}/chat/completions"


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        provider: ProviderName,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int,
        temperature: float,
        retries: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.endpoint = validate_provider_configuration(
            provider=provider,
            base_url=base_url,
            api_key=api_key,
            model=model,
        )
        self.provider = provider
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self.retries = retries
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = client is None
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def generate(self, messages: list[GenerationMessage]) -> GenerationResult:
        payload = {
            "model": self.model,
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
            "max_tokens": self.max_output_tokens,
            "temperature": self.temperature,
            "stream": False,
        }
        for attempt in range(self.retries + 1):
            try:
                response = await self._client.post(
                    self.endpoint,
                    headers=self._headers,
                    json=payload,
                )
            except httpx.TimeoutException as exc:
                if attempt < self.retries:
                    await asyncio.sleep(0.25)
                    continue
                raise ProviderTimeoutError("Generation provider timed out") from exc
            except httpx.TransportError as exc:
                if attempt < self.retries:
                    await asyncio.sleep(0.25)
                    continue
                raise ProviderUnavailableError("Generation provider is unavailable") from exc

            if response.status_code == 429 and attempt < self.retries:
                await asyncio.sleep(0.25)
                continue
            if response.status_code >= 500 and attempt < self.retries:
                await asyncio.sleep(0.25)
                continue
            self._raise_for_status(response.status_code)
            return self._parse_response(response)
        raise ProviderUnavailableError("Generation provider is unavailable")

    def _raise_for_status(self, status_code: int) -> None:
        if status_code in {401, 403}:
            raise InvalidCredentialsError("Generation provider credentials are invalid")
        if status_code == 402:
            raise InsufficientFundsError("Generation provider balance is insufficient")
        if status_code == 429:
            raise ProviderRateLimitError("Generation provider rate limit reached")
        if status_code == 408:
            raise ProviderTimeoutError("Generation provider timed out")
        if status_code >= 500:
            raise ProviderUnavailableError("Generation provider is unavailable")
        if status_code >= 400:
            raise InvalidProviderRequestError("Generation provider rejected the request")

    def _parse_response(self, response: httpx.Response) -> GenerationResult:
        try:
            payload: Any = response.json()
            choices = payload["choices"]
            content = choices[0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise TypeError
            usage = self._parse_usage(payload.get("usage"))
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise MalformedProviderResponseError(
                "Generation provider returned a malformed response"
            ) from exc
        if len(content) > self.max_output_tokens * 8 + 1000:
            raise MalformedProviderResponseError("Generation provider response exceeded limits")
        return GenerationResult(content=content.strip(), usage=usage)

    def _parse_usage(self, raw_usage: object) -> TokenUsage | None:
        if not isinstance(raw_usage, Mapping):
            return None

        def optional_int(key: str) -> int | None:
            value = raw_usage.get(key)
            return value if isinstance(value, int) and value >= 0 else None

        return TokenUsage(
            prompt_tokens=optional_int("prompt_tokens"),
            completion_tokens=optional_int("completion_tokens"),
            total_tokens=optional_int("total_tokens"),
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
