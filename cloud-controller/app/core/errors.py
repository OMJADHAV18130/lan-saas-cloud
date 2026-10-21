"""Consistent JSON error handling.

Every error leaving the API has the shape:

    {"error": {"code": "not_found", "message": "File not found",
               "details": [ ... ] | null}}

Internal details (stack traces, credentials, filesystem paths) are never
returned to the client; they are written to the server log only.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("cloud_controller.errors")


class AppError(Exception):
    """Base class for expected, safe-to-report application errors."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"

    def __init__(self, message: str, *, details: list | None = None,
                 status_code: int | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code


class ValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_error"


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class PermissionDenied(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class NotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class Conflict(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class PayloadTooLarge(AppError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    code = "payload_too_large"


class RateLimited(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"


class StorageUnavailable(AppError):
    """HDFS (the storage backend) is unreachable or returned an error."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "storage_unavailable"

    def __init__(self, message: str = "Storage backend is unavailable.",
                 *, details: list | None = None):
        super().__init__(message, details=details)


def _error_response(status_code: int, code: str, message: str,
                    details: list | None = None) -> JSONResponse:
    body = {"error": {"code": code, "message": message,
                      "details": details}}
    return JSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):  # noqa: ANN001
        return _error_response(exc.status_code, exc.code, exc.message,
                              exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        details = [
            {"field": ".".join(str(p) for p in err.get("loc", [])),
             "message": err.get("msg", "invalid value")}
            for err in exc.errors()
        ]
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "validation_error",
            "Request validation failed.",
            details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = {
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            405: "method_not_allowed",
        }.get(exc.status_code, "http_error")
        return _error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        incident = uuid.uuid4().hex[:12]
        logger.exception("Unhandled error [incident %s] on %s %s",
                         incident, request.method, request.url.path)
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "An unexpected server error occurred. "
            f"Reference: {incident}",
        )
