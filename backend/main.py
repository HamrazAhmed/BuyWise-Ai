"""
backend/main.py
FastAPI application entry point for BuyWise AI.

Deployment modes:
  - Local dev:    uvicorn main:app --reload --port 8000
  - Vercel:       Vercel Python functions (see /api/index.py and vercel.json at repo root)

Security controls implemented here (PRD §19):
  - CORS restricted to ALLOWED_ORIGIN env var
  - Request body size limit (10KB)
  - Rate limiting via slowapi (per-IP)
  - Secure HTTP headers via middleware
  - Centralized error responses in PRD format
  - No secrets in logs
"""

import logging
import os
import sys
import time
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# ─── Logging setup (no PII or secrets in logs) ───────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("buywise")

# Redact sensitive env vars from any accidental log lines
_REDACTED_KEYS = {"GEMINI_API_KEY", "DATABASE_URL", "SEARCH_API_KEY"}

# ─── App instance ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app):
    from data.runtime import ensure
    from api.research import ensure_local_worker, _workers
    await asyncio.to_thread(ensure)
    ensure_local_worker()
    try:
        yield
    finally:
        task = _workers.pop(asyncio.get_running_loop(), None)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


app = FastAPI(
    lifespan=lifespan,
    title="BuyWise AI API",
    version="0.1.0",
    description="Evidence-backed shopping decision assistant — backend API.",
    docs_url="/api/docs",      # Swagger UI (dev only; disable in prod if desired)
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ─── CORS ─────────────────────────────────────────────────────────────────────

ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "http://localhost:3000")
# In production this should be the Vercel frontend URL, e.g. https://buywise.vercel.app
ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGIN.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "X-Request-ID", "Last-Event-ID"],
    max_age=86400,
)

# ─── Secure headers middleware ─────────────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add recommended security headers to every response (PRD §19)."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        # CSP: allow only same-origin and API calls; adjust as needed
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        return response


app.add_middleware(SecurityHeadersMiddleware)

# ─── Request size limit middleware ─────────────────────────────────────────────

MAX_REQUEST_BODY_BYTES = 10 * 1024  # 10KB (PRD §19)


class RequestSizeLimitMiddleware:
    """Bound bodies even when Content-Length is missing or inaccurate."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] in ('GET', 'OPTIONS', 'HEAD'):
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        async def reject(code, message):
            response = JSONResponse(status_code=code, content={'error': {'code': 'INVALID_INPUT', 'message': message}})
            await response(scope, receive, send)
        length = headers.get(b'content-length')
        if length is not None:
            try:
                declared = int(length)
                if declared < 0: raise ValueError()
            except ValueError:
                return await reject(400, 'Invalid content length.')
            if declared > MAX_REQUEST_BODY_BYTES:
                return await reject(413, 'Request body too large (max 10KB).')
        body = bytearray()
        while True:
            try:
                message = await asyncio.wait_for(receive(), timeout=10)
            except asyncio.TimeoutError:
                return await reject(408, 'Request body timed out.')
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body', b''))
            if len(body) > MAX_REQUEST_BODY_BYTES:
                return await reject(413, 'Request body too large (max 10KB).')
            if not message.get('more_body', False): break
        delivered = False
        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()
        return await self.app(scope, bounded_receive, send)


app.add_middleware(RequestSizeLimitMiddleware)

# ─── Request logging / timing middleware ──────────────────────────────────────

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log each request with timing. Never logs request bodies or secrets."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        request_id = request.headers.get("X-Request-ID", "-")
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)
        # Log: method, path, status, duration — no body, no auth headers
        client = request.client.host if request.client else "unknown"
        logger.info(
            "req method=%s path=%s status=%d duration_ms=%d request_id=%s client=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
            client,
        )
        return response


app.add_middleware(RequestLoggingMiddleware)

# ─── Simple in-memory rate limiter ────────────────────────────────────────────
# For production, use Upstash Redis free tier [VERIFY availability and limits].
# This in-memory version works per-process (fine for Vercel serverless if each
# request is isolated, but not shared across instances).

import collections

_rate_limit_store: dict[str, collections.deque] = {}
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "30"))  # per window
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW", "60"))


def is_rate_limited(ip: str) -> bool:
    """Return True if the IP has exceeded the rate limit."""
    now = time.time()
    if os.getenv('DATABASE_URL', '').strip():
        import hashlib
        from data.runtime import ensure, reserve
        ensure()
        interval = int(now // RATE_LIMIT_WINDOW_SECONDS)
        bucket = 'http:' + hashlib.sha256(ip.encode()).hexdigest() + ':' + str(interval)
        return not reserve(bucket, RATE_LIMIT_REQUESTS, (interval + 1) * RATE_LIMIT_WINDOW_SECONDS)
    for key in list(_rate_limit_store):
        if not _rate_limit_store[key] or _rate_limit_store[key][-1] < now - RATE_LIMIT_WINDOW_SECONDS:
            del _rate_limit_store[key]
    if len(_rate_limit_store) >= 10000 and ip not in _rate_limit_store:
        return True
    window = _rate_limit_store.setdefault(ip, collections.deque())
    # Remove timestamps outside the window
    while window and window[0] < now - RATE_LIMIT_WINDOW_SECONDS:
        window.popleft()
    if len(window) >= RATE_LIMIT_REQUESTS:
        return True
    window.append(now)
    return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP rate limiting for all /api/* routes."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/") and request.method not in ("GET", "OPTIONS"):
            client_ip = request.client.host if request.client else "unknown"
            if await asyncio.to_thread(is_rate_limited, client_ip):
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": str(RATE_LIMIT_WINDOW_SECONDS)},
                    content={"error": {
                        "code": "RATE_LIMITED",
                        "message": "Too many requests. Please wait before trying again.",
                        "retry_after": RATE_LIMIT_WINDOW_SECONDS,
                    }},
                )
        return await call_next(request)


app.add_middleware(RateLimitMiddleware)

# ─── Global error handler ─────────────────────────────────────────────────────

from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException as FastAPIHTTPException


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return a PRD-format error on Pydantic validation failure."""
    return JSONResponse(
        status_code=422,
        content={"error": {
            "code": "SCHEMA_ERROR",
            "message": "Request validation failed.",
            "detail": [{"loc": list(e["loc"]), "type": e["type"], "msg": e["msg"]} for e in exc.errors()],
        }},
    )


@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(request: Request, exc: FastAPIHTTPException):
    """Pass through HTTPExceptions that already contain the error envelope."""
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    # Wrap plain string details
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "INTERNAL_ERROR", "message": str(exc.detail)}},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled %s for %s %s", type(exc).__name__, request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": {
            "code": "INTERNAL_ERROR",
            "message": "An unexpected server error occurred.",
        }},
    )

# ─── Routers ──────────────────────────────────────────────────────────────────

from api.health import router as health_router
from api.analyze import router as analyze_router
from api.research import router as research_router   # Steps 5-6: pipeline, product, comparison
from api.follow_up import router as follow_up_router  # Step 7: follow-up Q&A

app.include_router(health_router, prefix="/api")
app.include_router(analyze_router, prefix="/api")
app.include_router(research_router, prefix="/api")
app.include_router(follow_up_router, prefix="/api")

# ─── Root redirect ─────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    return {"message": "BuyWise AI API — see /api/docs for documentation."}


# ─── Dev server ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn  # type: ignore
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=True,
        log_level="info",
    )
