"""Bearer token middleware. Every endpoint requires `Authorization: Bearer <token>`.

Next.js server components/route handlers inject `FASTAPI_SERVICE_TOKEN` on every
request; no other client ever talks to this API. User-scoped endpoints additionally
check for a signed Clerk-user header (see `require_clerk_user`).
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from miami_common.settings import get_settings


def verify_service_token(
    authorization: str | None = Header(default=None),
) -> None:
    settings = get_settings()
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_bearer")
    presented = authorization.split(" ", 1)[1].strip()
    expected = settings.fastapi_service_token
    if not hmac.compare_digest(presented, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token")


def require_clerk_user(
    x_clerk_user_id: str | None = Header(default=None),
) -> str:
    if not x_clerk_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_user_context")
    return x_clerk_user_id
