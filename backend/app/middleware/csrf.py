"""Double-submit CSRF protection for browser-originated state changes."""

import hmac
import secrets

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import settings

CSRF_COOKIE = "aperture_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # CSRF is a browser threat. Origin preserves non-browser service-token clients.
        if (
            request.method not in SAFE_METHODS
            and request.headers.get("origin")
            and request.url.path != "/api/v1/auth/login"
        ):
            cookie = request.cookies.get(CSRF_COOKIE)
            header = request.headers.get(CSRF_HEADER)
            if not cookie or not header or not hmac.compare_digest(cookie, header):
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "detail": {
                            "code": "CSRF_FAILED",
                            "message": "Missing or invalid CSRF token",
                        }
                    },
                )
        response = await call_next(request)
        if not request.cookies.get(CSRF_COOKIE):
            response.set_cookie(
                CSRF_COOKIE,
                secrets.token_urlsafe(32),
                secure=settings.session_cookie_secure,
                httponly=False,
                samesite="strict",
                path="/",
            )
        return response
