from app.core.settings import Settings
from app.generation.openai_compatible import OpenAICompatibleProvider
from app.generation.provider import GenerationProvider


def create_generation_provider(settings: Settings) -> GenerationProvider | None:
    if settings.chat_provider == "disabled":
        return None
    api_key = settings.chat_api_key
    if api_key is None:
        raise RuntimeError("Chat provider is enabled without an API key")
    try:
        return OpenAICompatibleProvider(
            provider=settings.chat_provider,
            base_url=settings.chat_base_url,
            api_key=api_key.get_secret_value(),
            model=settings.chat_model,
            timeout_seconds=settings.chat_timeout_seconds,
            max_output_tokens=settings.chat_max_output_tokens,
            temperature=settings.chat_temperature,
            retries=settings.chat_provider_retries,
        )
    except ValueError as exc:
        raise RuntimeError("Chat provider configuration is invalid") from exc
