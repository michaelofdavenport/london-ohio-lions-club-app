# backend/app/authz_errors.py
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """
    IMPORTANT:
    - Preserve the real HTTP status code (404/401/403/etc).
    - Do NOT convert everything into 500.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Catch true unexpected errors.
    """
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
    )
