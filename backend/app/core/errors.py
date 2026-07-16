from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.details = details or {}


class DependencyUnavailableError(AppError):
    def __init__(self, dependency: str) -> None:
        super().__init__(
            "dependency_unavailable",
            "A required service is temporarily unavailable.",
            status_code=503,
            retryable=True,
            details={"dependency": dependency},
        )
