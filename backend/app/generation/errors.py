class GenerationError(RuntimeError):
    """Base generation failure with no provider response content."""


class InvalidCredentialsError(GenerationError):
    pass


class InsufficientFundsError(GenerationError):
    pass


class ProviderRateLimitError(GenerationError):
    pass


class ProviderTimeoutError(GenerationError):
    pass


class ProviderUnavailableError(GenerationError):
    pass


class MalformedProviderResponseError(GenerationError):
    pass


class InvalidProviderRequestError(GenerationError):
    pass
