from __future__ import annotations

import re
import sys
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any
from uuid import UUID, uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="unknown")
_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SENSITIVE_KEYS = frozenset(
    {"authorization", "cookie", "password", "secret", "token", "access_token", "refresh_token"}
)


def redact_sensitive(
    _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in tuple(event_dict):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def add_correlation_id(
    _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    event_dict["correlation_id"] = correlation_id_var.get()
    return event_dict


def configure_logging(level: str) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_correlation_id,
            redact_sensitive,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, header_name: str = "X-Correlation-ID") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied = request.headers.get(self.header_name)
        correlation_id = supplied if supplied and _SAFE_ID.fullmatch(supplied) else str(uuid4())
        token = correlation_id_var.set(correlation_id)
        try:
            response = await call_next(request)
            response.headers[self.header_name] = correlation_id
            return response
        finally:
            correlation_id_var.reset(token)


def get_correlation_id() -> str:
    value = correlation_id_var.get()
    try:
        return str(UUID(value)) if value != "unknown" else value
    except ValueError:
        return value
