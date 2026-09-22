"""The guest-facing half: no sign-in, open to the public internet.

Everything here is reachable by anyone with the link, so it is written
defensively: the payload is size-capped before it is parsed, every field
is re-validated server-side regardless of what the browser enforced, and
submissions are rate-limited per IP and in total.

The producer side lives in `routes_review.py` and is behind SSO.
"""
from __future__ import annotations

import json
import secrets
import time
from collections import deque
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.content_models import StoreOption, Submission
from app.db import get_session
from app.frontend import render_page
from app.games import ValidationError, validate_submission

router = APIRouter(tags=["public"])

# A submission with every game filled in is roughly 40 KB of text. 512 KB
# leaves generous headroom while keeping a hostile payload from ever
# reaching the JSON parser.
MAX_BODY_BYTES = 512 * 1024

# Sliding-window limits. This is per process: Railway runs this app as a
# single service, so one process sees every request. If this app is ever
# scaled to multiple replicas these counters become per-replica and the
# effective limit multiplies — move them to Postgres or Redis at that point.
PER_IP_HOURLY = 5
PER_IP_DAILY = 20
GLOBAL_HOURLY = 200

# Bots fill every field they find, including ones humans never see, and
# they submit instantly. Both are cheap signals and neither inconveniences
# a real person.
HONEYPOT_FIELD = "website"
MIN_FILL_SECONDS = 5

_ip_hits: dict[str, deque[float]] = {}
_global_hits: deque[float] = deque()


def _client_ip(request: Request) -> str:
    """Best-effort client IP behind Railway's proxy."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "")[:64]


def _prune(dq: deque[float], window: float, now: float) -> None:
    while dq and now - dq[0] > window:
        dq.popleft()


def _check_rate(ip: str) -> None:
    now = time.time()
    _prune(_global_hits, 3600, now)
    if len(_global_hits) >= GLOBAL_HOURLY:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "We're getting an unusual number of submissions right now. "
            "Please try again in a little while.",
        )
    hits = _ip_hits.setdefault(ip, deque())
    _prune(hits, 86400, now)
    recent_hour = sum(1 for t in hits if now - t <= 3600)
    if recent_hour >= PER_IP_HOURLY or len(hits) >= PER_IP_DAILY:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "That's a lot of submissions from one place. If this is a "
            "mistake, email us and we'll sort it out.",
        )
    # Keep the table from growing without bound on a busy day.
    if len(_ip_hits) > 5000:
        for k in [k for k, v in _ip_hits.items() if not v]:
            _ip_hits.pop(k, None)


def _record_rate(ip: str) -> None:
    now = time.time()
    _ip_hits.setdefault(ip, deque()).append(now)
    _global_hits.append(now)


async def active_store_names(db: AsyncSession) -> list[str]:
    rows = (
        await db.execute(
            select(StoreOption)
            .where(StoreOption.active == True)  # noqa: E712
            .order_by(StoreOption.sort_key)
        )
    ).scalars().all()
    return [r.name for r in rows]


@router.get("/", response_class=HTMLResponse)
async def public_form(request: Request) -> HTMLResponse:
    """The submission form. Deliberately unauthenticated."""
    settings = get_settings()
    if not settings.public_form_enabled:
        return HTMLResponse(
            render_page({"mode": "closed"}),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return HTMLResponse(render_page({"mode": "public"}))


@router.get("/api/stores")
async def api_stores(db: AsyncSession = Depends(get_session)) -> JSONResponse:
    return JSONResponse({"stores": await active_store_names(db)})


@router.post("/api/submissions", status_code=status.HTTP_201_CREATED)
async def api_submit(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> JSONResponse:
    settings = get_settings()
    if not settings.public_form_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "The form is closed right now.")

    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            "That submission is too large.")
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            "That submission is too large.")
    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed request.") from None
    if not isinstance(payload, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed request.")

    ip = _client_ip(request)
    _check_rate(ip)

    # Quiet bot checks. Both answer with the same generic message a real
    # person would never see, and neither tells a bot which one it tripped.
    if str(payload.get(HONEYPOT_FIELD) or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Submission rejected.")
    try:
        elapsed = float(payload.get("elapsedMs") or 0)
    except (TypeError, ValueError):
        elapsed = 0
    if elapsed < MIN_FILL_SECONDS * 1000:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Submission rejected.")

    try:
        record = validate_submission(payload)
    except ValidationError as e:
        return JSONResponse(
            {"error": "validation", "problems": e.problems},
            status_code=422,
        )

    # A store that isn't on the list is refused rather than quietly kept,
    # so the producer view's store filter stays meaningful.
    stores = await active_store_names(db)
    if stores and record["location"] not in stores:
        return JSONResponse(
            {"error": "validation", "problems": ["Pick a store from the list."]},
            status_code=422,
        )

    reference = "GBGS-" + secrets.token_hex(4).upper()
    sub = Submission(
        reference=reference,
        name=record["name"],
        email=record["email"],
        group_name=record["group"],
        store=record["location"],
        event_date=record["event_date"],
        games_csv=",".join(record["games"]),
        content_json=json.dumps(record["content"], ensure_ascii=False),
        source_ip=ip,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(sub)
    await db.commit()
    _record_rate(ip)

    return JSONResponse({"reference": reference}, status_code=status.HTTP_201_CREATED)
