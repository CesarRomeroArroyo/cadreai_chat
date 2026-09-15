from collections.abc import Callable

import httpx
import pytest

from app.generation.errors import (
    InsufficientFundsError,
    InvalidCredentialsError,
    InvalidProviderRequestError,
    MalformedProviderResponseError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.generation.models import GenerationMessage
from app.generation.openai_compatible import OpenAICompatibleProvider


def make_provider(
    handler: Callable[[httpx.Request], httpx.Response], *, model: str = "test-model"
) -> OpenAICompatibleProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenAICompatibleProvider(
        provider="openai",
        base_url="https://api.openai.com/v1",
        api_key="test-api-key",
        model=model,
        timeout_seconds=1,
        max_output_tokens=100,
        temperature=0.1,
        retries=1,
        client=client,
    )


@pytest.mark.anyio
async def test_generates_with_bounded_openai_compatible_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.openai.com/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-api-key"
        payload = __import__("json").loads(request.content)
        assert payload == {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Question"}],
            "max_completion_tokens": 100,
            "temperature": 0.1,
            "stream": False,
        }
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Verified answer"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
            },
        )

    provider = make_provider(handler)

    result = await provider.generate([GenerationMessage(role="user", content="Question")])

    assert result.content == "Verified answer"
    assert result.usage is not None
    assert result.usage.total_tokens == 13
    await provider.aclose()


@pytest.mark.anyio
async def test_uses_modern_parameters_for_gpt_5_models() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        assert payload == {
            "model": "gpt-5.6-luna",
            "messages": [
                {"role": "developer", "content": "Grounding rules"},
                {"role": "user", "content": "Question"},
            ],
            "max_completion_tokens": 100,
            "stream": False,
        }
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": "Verified answer"}}]},
        )

    provider = make_provider(handler, model="gpt-5.6-luna")

    result = await provider.generate(
        [
            GenerationMessage(role="system", content="Grounding rules"),
            GenerationMessage(role="user", content="Question"),
        ]
    )

    assert result.content == "Verified answer"
    await provider.aclose()


@pytest.mark.anyio
async def test_retries_one_transient_failure() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, request=request)
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": "Recovered"}}]},
        )

    provider = make_provider(handler)

    result = await provider.generate([GenerationMessage(role="user", content="Question")])

    assert result.content == "Recovered"
    assert attempts == 2
    await provider.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (401, InvalidCredentialsError),
        (402, InsufficientFundsError),
        (408, ProviderTimeoutError),
        (429, ProviderRateLimitError),
        (500, ProviderUnavailableError),
        (400, InvalidProviderRequestError),
    ],
)
async def test_maps_provider_status_without_exposing_response(
    status_code: int, error_type: type[Exception]
) -> None:
    provider = make_provider(
        lambda request: httpx.Response(
            status_code,
            request=request,
            text="secret provider response",
        )
    )

    with pytest.raises(error_type, match="provider|Provider") as caught:
        await provider.generate([GenerationMessage(role="user", content="Question")])

    assert "secret provider response" not in str(caught.value)
    await provider.aclose()


@pytest.mark.anyio
async def test_rejects_malformed_success_response() -> None:
    provider = make_provider(lambda request: httpx.Response(200, request=request, json={}))

    with pytest.raises(MalformedProviderResponseError):
        await provider.generate([GenerationMessage(role="user", content="Question")])

    await provider.aclose()


def test_rejects_mismatched_provider_base_url() -> None:
    with pytest.raises(ValueError, match="base URL"):
        OpenAICompatibleProvider(
            provider="openrouter",
            base_url="https://api.openai.com/v1",
            api_key="test-api-key",
            model="test-model",
            timeout_seconds=1,
            max_output_tokens=100,
            temperature=0.1,
            retries=0,
        )
