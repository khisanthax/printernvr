from __future__ import annotations

import base64
import binascii
import hmac
import os

from starlette.datastructures import Headers
from starlette.responses import JSONResponse


def credentials_match(header: str, password: str) -> bool:
    scheme, _, credential = header.partition(" ")
    if scheme.lower() != "basic":
        return False
    try:
        decoded = base64.b64decode(credential, validate=True)
    except (ValueError, binascii.Error):
        return False
    return hmac.compare_digest(decoded, b"admin:" + password.encode("utf-8"))


class AccessBoundary:
    def __init__(self, app):
        self.app = app
        self.password = os.getenv("APP_ACCESS_PASSWORD", "")
        bind = os.getenv("APP_BIND_ADDRESS", "127.0.0.1")
        if bind not in {"127.0.0.1", "::1"} and not self.password:
            raise RuntimeError("APP_ACCESS_PASSWORD is required with a non-loopback bind address")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == "/health":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        if self.password and not credentials_match(headers.get("authorization", ""), self.password):
            response = JSONResponse(
                {"detail": "Authentication required"}, status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Printer NVR", charset="UTF-8"'},
            )
            await response(scope, receive, send)
            return
        if scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            origin = headers.get("origin")
            host = headers.get("host")
            allowed = {f"{scope['scheme']}://{host}"} if host else set()
            if headers.get("sec-fetch-site") == "cross-site" or (origin and origin not in allowed):
                response = JSONResponse({"detail": "Cross-origin changes are denied"}, status_code=403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
