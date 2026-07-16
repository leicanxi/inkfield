from __future__ import annotations

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import AppError
from app.core.observability import get_correlation_id
from app.core.schemas import ErrorBody, ErrorEnvelope

logger = structlog.get_logger(__name__)


def _response(error: AppError) -> JSONResponse:
    body = ErrorEnvelope(
        error=ErrorBody(
            code=error.code,
            message=error.message,
            retryable=error.retryable,
            correlation_id=get_correlation_id(),
            details=error.details,
        )
    )
    return JSONResponse(status_code=error.status_code, content=body.model_dump(mode="json"))


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        await logger.awarning("application_error", error_code=exc.code)
        return _response(exc)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        safe_details = {
            "fields": [
                {"location": list(item["loc"]), "type": item["type"]} for item in exc.errors()
            ]
        }
        return _response(
            AppError(
                "request_validation_failed",
                "The request does not match the API contract.",
                status_code=422,
                details=safe_details,
            )
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        await logger.aexception("unexpected_error", exception_type=type(exc).__name__)
        return _response(
            AppError(
                "internal_error",
                "An unexpected error occurred.",
                status_code=500,
                retryable=False,
            )
        )
