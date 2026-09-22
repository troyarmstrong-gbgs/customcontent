"""The producer view: everything behind Curiosity Games SSO.

Access is the platform's own — a signed-in person with a role on this
app. There is no passcode and no second login; `require_reviewer` is the
single gate every route here goes through.

Editors and admins may change a submission; viewers may read it. Delete
is admin-only, because it is the one irreversible action.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.content_models import StoreOption, Submission
from app.csv_export import build_csv, export_specs, filename_for, find_spec
from app.db import get_session
from app.frontend import render_page
from app.games import GAMES, validate_game

router = APIRouter(tags=["review"])

VIEW_ROLES = {"viewer", "editor", "admin"}
EDIT_ROLES = {"editor", "admin"}


def _session_user(request: Request) -> dict:
    user = request.session.get("user") or {}
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required")
    return user


def _role(user: dict) -> str:
    role = (user.get("app_role") or "pending").lower()
    if user.get("is_admin") or user.get("is_super_admin"):
        return "admin"
    return role


def require_reviewer(request: Request) -> dict:
    """Signed in and granted a role on this app. Deny by default."""
    user = _session_user(request)
    if _role(user) not in VIEW_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this app")
    return user


def require_editor(request: Request) -> dict:
    user = require_reviewer(request)
    if _role(user) not in EDIT_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Read-only access")
    return user


def require_admin(request: Request) -> dict:
    user = require_reviewer(request)
    if _role(user) != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


def _serialize(sub: Submission) -> dict:
    try:
        content = json.loads(sub.content_json or "{}")
    except ValueError:
        content = {}
    return {
        "id": sub.id,
        "reference": sub.reference,
        "name": sub.name,
        "email": sub.email,
        "group": sub.group_name,
        "location": sub.store,
        "eventDate": sub.event_date,
        "games": sub.game_list(),
        "content": content,
        "specialEventId": sub.special_event_id,
        "status": "loaded" if sub.uploaded_to_chippy else "new",
        "submittedAt": (sub.submitted_at or datetime.now(timezone.utc)).isoformat(),
    }


async def _get(db: AsyncSession, sub_id: int) -> Submission:
    sub = (
        await db.execute(select(Submission).where(Submission.id == sub_id))
    ).scalar_one_or_none()
    if not sub:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such submission")
    return sub


# --- pages -----------------------------------------------------------------


@router.get("/review", response_class=HTMLResponse)
async def review_page(request: Request) -> HTMLResponse:
    """The producer view. Bounces to SSO when signed out."""
    user = request.session.get("user") or {}
    if not user:
        return HTMLResponse(render_page({"mode": "signin"}))
    if _role(user) not in VIEW_ROLES:
        return HTMLResponse(render_page({"mode": "norole",
                                         "email": user.get("email", "")}),
                            status_code=status.HTTP_403_FORBIDDEN)
    return HTMLResponse(render_page({
        "mode": "review",
        "email": user.get("email", ""),
        "name": user.get("name", ""),
        "canEdit": _role(user) in EDIT_ROLES,
        "isAdmin": _role(user) == "admin",
    }))


# --- submissions -----------------------------------------------------------


@router.get("/api/review/submissions")
async def list_submissions(
    _user: dict = Depends(require_reviewer),
    db: AsyncSession = Depends(get_session),
) -> JSONResponse:
    rows = (
        await db.execute(
            select(Submission).order_by(Submission.submitted_at.desc()).limit(500)
        )
    ).scalars().all()
    return JSONResponse({"submissions": [_serialize(r) for r in rows]})


@router.patch("/api/review/submissions/{sub_id}")
async def patch_submission(
    sub_id: int,
    request: Request,
    _user: dict = Depends(require_editor),
    db: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Update the reviewer-owned fields, and optionally the content.

    Content coming back in is re-validated exactly like a fresh
    submission, so an accepted spelling fix can't smuggle in an
    over-length answer.
    """
    try:
        payload = json.loads(await request.body() or b"{}")
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed request") from None

    sub = await _get(db, sub_id)

    if "specialEventId" in payload:
        sub.special_event_id = str(payload["specialEventId"] or "").strip()[:120]
    if "status" in payload:
        sub.uploaded_to_chippy = payload["status"] == "loaded"
    if "eventDate" in payload:
        sub.event_date = str(payload["eventDate"] or "").strip()[:10]
    if "location" in payload:
        sub.store = str(payload["location"] or "").strip()[:160]

    if "content" in payload and isinstance(payload["content"], dict):
        content = {}
        problems: list[str] = []
        for gid in sub.game_list():
            if gid not in GAMES:
                continue
            rows, game_problems = validate_game(gid, payload["content"].get(gid))
            content[gid] = rows
            problems.extend(game_problems)
        # A reviewer is allowed to leave a submission imperfect (they may
        # be mid-edit), but never over a hard limit — validate_game has
        # already truncated those.
        sub.content_json = json.dumps(content, ensure_ascii=False)

    await db.commit()
    await db.refresh(sub)
    return JSONResponse({"submission": _serialize(sub)})


@router.delete("/api/review/submissions/{sub_id}")
async def delete_submission(
    sub_id: int,
    _user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> JSONResponse:
    sub = await _get(db, sub_id)
    await db.delete(sub)
    await db.commit()
    return JSONResponse({"deleted": sub_id})


# --- CSV -------------------------------------------------------------------


@router.get("/api/review/submissions/{sub_id}/csv/{game_id}/{slug}")
async def download_csv(
    sub_id: int,
    game_id: str,
    slug: str,
    _user: dict = Depends(require_reviewer),
    db: AsyncSession = Depends(get_session),
) -> Response:
    spec = find_spec(game_id, slug)
    if not spec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such export")
    sub = await _get(db, sub_id)
    try:
        content = json.loads(sub.content_json or "{}")
    except ValueError:
        content = {}
    text = build_csv(spec, content.get(game_id) or [], sub.special_event_id)
    name = filename_for(spec, date.today())
    return Response(
        content=text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/api/review/exports/{game_id}")
async def list_exports(
    game_id: str,
    _user: dict = Depends(require_reviewer),
) -> JSONResponse:
    return JSONResponse({
        "exports": [{"slug": s["slug"], "label": s["label"]}
                    for s in export_specs(game_id)]
    })


# --- stores ----------------------------------------------------------------


@router.get("/api/review/stores")
async def review_stores(
    _user: dict = Depends(require_reviewer),
    db: AsyncSession = Depends(get_session),
) -> JSONResponse:
    rows = (
        await db.execute(select(StoreOption).order_by(StoreOption.sort_key))
    ).scalars().all()
    return JSONResponse({
        "stores": [{"id": r.id, "name": r.name, "active": r.active} for r in rows]
    })


@router.post("/api/review/stores")
async def add_store(
    request: Request,
    _user: dict = Depends(require_editor),
    db: AsyncSession = Depends(get_session),
) -> JSONResponse:
    payload = json.loads(await request.body() or b"{}")
    name = " ".join(str(payload.get("name") or "").split()).strip()[:160]
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A store name is required")
    existing = (
        await db.execute(select(StoreOption).where(
            StoreOption.name.ilike(name)))
    ).scalar_one_or_none()
    if existing:
        if not existing.active:
            existing.active = True
            await db.commit()
            return JSONResponse({"restored": existing.name})
        raise HTTPException(status.HTTP_409_CONFLICT, "That store is already listed")
    db.add(StoreOption(name=name, sort_key=name.lower()))
    await db.commit()
    return JSONResponse({"added": name}, status_code=status.HTTP_201_CREATED)


@router.delete("/api/review/stores/{store_id}")
async def retire_store(
    store_id: int,
    _user: dict = Depends(require_editor),
    db: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Retire rather than delete, so old submissions keep their store name."""
    store = (
        await db.execute(select(StoreOption).where(StoreOption.id == store_id))
    ).scalar_one_or_none()
    if not store:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such store")
    store.active = False
    await db.commit()
    return JSONResponse({"retired": store.name})


# --- spelling and grammar --------------------------------------------------

SPELLCHECK_PROMPT = (
    "You are proofreading trivia content written for a live game show. Check each "
    "item for spelling, grammar, punctuation and capitalization. Keep the writer's "
    "voice and American English. Do not rewrite for style or shorten unless "
    "something is actually wrong. A corrected item MUST stay within its character "
    "limit.\n\n"
    "Reply with ONLY a JSON array. One object per item that needs a change:\n"
    '[{"id":"<id>","corrected":"<full corrected text>","reason":"<max 12 words>"}]\n'
    "Return [] if everything is clean. Never include items you did not change.\n\n"
    "ITEMS:\n"
)


@router.post("/api/review/spellcheck")
async def spellcheck(
    request: Request,
    _user: dict = Depends(require_editor),
) -> JSONResponse:
    """Proxy a proofreading pass to the Claude API.

    The key lives on the server; the browser never sees it. Items come
    from the page so the model only ever reads this submission's text.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Spelling check isn't configured on this app.")
    payload = json.loads(await request.body() or b"{}")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return JSONResponse({"suggestions": []})
    # Cap what we'll forward — a whole submission is ~60 items.
    items = items[:200]
    slim = [
        {
            "id": str(i.get("id", ""))[:80],
            "limit": int(i.get("limit") or 0),
            "text": str(i.get("text", ""))[:600],
        }
        for i in items
        if isinstance(i, dict)
    ]

    body = {
        "model": settings.spellcheck_model,
        "max_tokens": 4096,
        "messages": [{
            "role": "user",
            "content": SPELLCHECK_PROMPT + json.dumps(slim, ensure_ascii=False),
        }],
    }
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
            )
    except httpx.HTTPError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "Couldn't reach the proofreading service.") from None
    if resp.status_code >= 400:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f"Proofreading service returned {resp.status_code}.")

    text = ""
    for block in resp.json().get("content", []):
        if block.get("type") == "text":
            text += block.get("text", "")
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        return JSONResponse({"suggestions": []})
    try:
        parsed = json.loads(text[start:end + 1])
    except ValueError:
        return JSONResponse({"suggestions": []})

    by_id = {i["id"]: i for i in slim}
    out = []
    for s in parsed if isinstance(parsed, list) else []:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("id", ""))
        item = by_id.get(sid)
        corrected = s.get("corrected")
        if not item or not isinstance(corrected, str):
            continue
        if item["limit"]:
            corrected = corrected[: item["limit"]]
        if corrected.strip() == item["text"].strip():
            continue
        out.append({
            "id": sid,
            "corrected": corrected,
            "reason": str(s.get("reason") or "Spelling and grammar.")[:120],
        })
    return JSONResponse({"suggestions": out})
