# app/authz_errors.py
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def _wants_html(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    # browsers usually send text/html
    return "text/html" in accept


def _detail_code(exc: StarletteHTTPException) -> str | None:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        code = detail.get("code")
        if isinstance(code, str):
            return code
    return None


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # Unauthenticated → send to login page in browser
    if exc.status_code == 401:
        if _wants_html(request):
            return RedirectResponse(url="/static/index.html", status_code=303)
        return JSONResponse(status_code=401, content={"detail": exc.detail})

    # Forbidden → if it's PRO_REQUIRED and browser, send to upgrade page
    if exc.status_code == 403:
        if _wants_html(request) and _detail_code(exc) == "PRO_REQUIRED":
            return RedirectResponse(url="/static/upgrade_pro.html", status_code=303)
        return JSONResponse(status_code=403, content={"detail": exc.detail})

    # Everything else: normal JSON
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
