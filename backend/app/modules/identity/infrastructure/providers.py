from app.core.errors import AppError
from app.modules.identity.domain.entities import ProviderIdentity


class UnconfiguredWeChatProvider:
    async def exchange_code(self, code: str) -> ProviderIdentity:
        del code
        raise AppError(
            "AUTH_PROVIDER_UNAVAILABLE",
            "WeChat login is not configured for this environment.",
            status_code=503,
            retryable=True,
        )
