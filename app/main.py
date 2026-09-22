"""FastAPI entrypoint — GBGS Custom Content Submission Form.

Two halves, one app:

  /        the submission form, open to the public internet
  /review  the producer view, behind Curiosity Games SSO

Everything under /api/review/* requires a signed-in person with a role on
this app. Everything under /api/* that isn't /api/review/* is public and
is written to assume hostile input.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.content_models import StoreOption
from app.db import SessionLocal, init_db
from app.routes_admin import router as admin_router
from app.routes_auth import router as auth_router
from app.routes_permissions import router as permissions_router
from app.routes_public import router as public_router
from app.routes_review import router as review_router

settings = get_settings()
log = logging.getLogger(__name__)

# Seeded into `store_options` the first time the app starts against an
# empty table. After that the list is maintained from the producer view
# and this is never consulted again.
SEED_STORES = [
    "Atlanta", "Birmingham", "Dania Beach", "East Rutherford", "Hanover",
    "Honolulu", "Houston", "Las Vegas (Area15)", "Las Vegas (Forum Shops)",
    "Minneapolis", "Murray", "Nashville — Opry Mills", "New York City",
    "Oak Brook", "Orlando", "Panama City Beach", "Pigeon Forge", "Richmond",
    "San Francisco", "San Jose", "Schaumburg", "Seattle (Downtown)",
    "Seattle (Southcenter)", "St. Louis", "The Colony", "Washington, DC",
]


async def seed_stores() -> None:
    async with SessionLocal() as db:
        count = (await db.execute(select(func.count(StoreOption.id)))).scalar_one()
        if count:
            return
        for name in SEED_STORES:
            db.add(StoreOption(name=name, sort_key=name.lower()))
        await db.commit()
        log.info("Seeded %d stores.", len(SEED_STORES))


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
        await seed_stores()
    except Exception:
        # Never block the health check on a database that isn't up yet —
        # the first deploy races Postgres coming online.
        log.exception("Startup DB work failed; DB-backed pages may 500.")
    yield


app = FastAPI(title="GBGS Custom Content", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site="lax",
    https_only=settings.public_url.startswith("https://"),
    max_age=60 * 60 * 8,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Order matters only for readability; the paths don't overlap.
app.include_router(auth_router)
app.include_router(permissions_router)
app.include_router(admin_router)
app.include_router(review_router)
app.include_router(public_router)


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Headers that matter on a page anyone on the internet can open."""
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault(
        "Content-Security-Policy",
        # The page's CSS and JS are inline; fonts come from Google; images
        # are our own. Nothing else loads, and nothing may frame us.
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'",
    )
    return resp


@app.exception_handler(404)
async def not_found(request: Request, exc):  # noqa: ANN001
    """Send stray links to the form rather than a bare JSON 404."""
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
