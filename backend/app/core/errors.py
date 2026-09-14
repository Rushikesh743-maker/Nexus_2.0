"""Consistent, structured API errors.

Every v1 error response has the same shape:

    { "error": { "code": "CASE_NOT_FOUND", "message": "...", "details": {} } }

Codes are stable strings the front end can branch on; messages are safe to
show to the user (they never contain stack traces or secrets).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("nexus.api")


class ApiError(Exception):
    """Application-level error with a stable machine-readable code."""

    def __init__(self, code: str, message: str, http_status: int = 400,
                 details: dict | None = None,
                 headers: dict[str, str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details or {}
        self.headers = headers or {}

    def to_body(self) -> dict:
        return {"error": {"code": self.code, "message": self.message,
                          "details": self.details}}


def not_found(code: str = "NOT_FOUND", message: str = "Resource not found.") -> None:
    raise ApiError(code, message, status.HTTP_404_NOT_FOUND)


def database_unavailable() -> None:
    raise ApiError(
        "DATABASE_UNAVAILABLE",
        "The platform database is not reachable. Check the backend logs and "
        "that PostgreSQL is running, then retry.",
        status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def unauthenticated() -> None:
    raise ApiError(
        "UNAUTHENTICATED",
        "Authentication required. Sign in and retry.",
        status.HTTP_401_UNAUTHORIZED,
    )


def forbidden(permission: str) -> None:
    raise ApiError(
        "FORBIDDEN",
        f"You do not have the '{permission}' permission for this action.",
        status.HTTP_403_FORBIDDEN,
    )


_STATUS_MESSAGES = {
    400: "Bad request.",
    401: "Not authenticated.",
    403: "Not allowed.",
    404: "Not found.",
    405: "Method not allowed.",
    409: "Conflict.",
    422: "Validation error.",
    500: "Internal server error.",
    503: "Service unavailable.",
}


def register_error_handlers(app: FastAPI) -> None:
    """Install the shared handlers on a FastAPI app."""

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):  # noqa: ANN001
        if exc.http_status >= 500:
            logger.error("API error %s on %s %s: %s", exc.code, request.method,
                         request.url.path, exc.message)
        else:
            logger.info("API %s %s -> %s (%s)", request.method, request.url.path,
                        exc.http_status, exc.code)
        return JSONResponse(status_code=exc.http_status, content=exc.to_body(),
                            headers=exc.headers or None)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):  # noqa: ANN001
        message = _STATUS_MESSAGES.get(exc.status_code, str(exc.detail))
        body = {"error": {"code": f"HTTP_{exc.status_code}", "message": message}}
        if exc.headers and "WWW-Authenticate" in exc.headers and exc.status_code == 401:
            return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):  # noqa: ANN001
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "VALIDATION_ERROR",
                               "message": "The request could not be validated.",
                               "details": {"fields": exc.errors()}}},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):  # noqa: ANN001
        # Log the full traceback server-side; return nothing sensitive.
        logger.exception("Unhandled error on %s %s: %s", request.method,
                         request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR",
                               "message": "Something went wrong on our side. "
                                          "The error has been logged."}},
        )
