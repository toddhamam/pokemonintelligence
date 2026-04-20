"""FastAPI app. Every endpoint requires the bearer service token; there are no
anonymous routes. Next.js is the sole client and injects the token server-side.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from miami_api.auth import verify_service_token
from miami_api.routers import alerts, analytics, catalog, history, rankings
from miami_common.logging import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

app = FastAPI(
    title="Miami — Pokemon Market Intelligence",
    version="0.1.0",
    dependencies=[Depends(verify_service_token)],
)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod to Vercel origin
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request, exc):  # type: ignore[no-untyped-def]
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=429, content={"detail": "rate_limited"})


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(catalog.router, prefix="/v1")
app.include_router(history.router, prefix="/v1")
app.include_router(rankings.router, prefix="/v1")
app.include_router(analytics.router, prefix="/v1")
app.include_router(alerts.router, prefix="/v1")
