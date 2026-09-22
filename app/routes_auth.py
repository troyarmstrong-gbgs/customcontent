"""Sign-in / sign-out routes that talk to the Curiosity Games service app.

Flow:
  GET  /auth/sso/login    -> redirect to service app's /auth/authorize
  GET  /auth/sso/callback -> static page that pulls id_token from URL
                             fragment and POSTs it to /auth/sso/complete
  POST /auth/sso/complete -> verify JWT, set session, redirect home
  GET  /auth/logout       -> clear session, redirect home
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import fetch_user_group_emails, resolve_role_on_login
from app.config import get_settings
from app.db import get_session
from app.models import LocalUser
from app.sso import TokenError, verify_sso_id_token

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/sso/login")
async def sso_login(request: Request):
    """Kick off SSO: store anti-CSRF state in a cookie, redirect to service app."""
    s = get_settings()
    state = secrets.token_urlsafe(24)
    redirect_uri = f"{s.public_url}/auth/sso/callback"
    query = urlencode(
        {
            "client_id": s.sso_client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "response_type": "id_token",
            "scope": "openid email profile",
        }
    )
    resp = RedirectResponse(
        url=f"{s.sso_authorization_url}?{query}", status_code=status.HTTP_303_SEE_OTHER
    )
    resp.set_cookie(
        "sso_state", state, httponly=True, secure=s.public_url.startswith("https://"),
        samesite="lax", max_age=600, path="/auth/sso",
    )
    return resp


@router.get("/sso/callback", response_class=HTMLResponse)
async def sso_callback(request: Request):
    """The id_token lives in the URL fragment, which servers cannot see.

    Render a tiny page that extracts it client-side and POSTs to /complete.
    """
    return templates.TemplateResponse(request, "callback.html", {})


@router.post("/sso/complete")
async def sso_complete(
    request: Request,
    id_token: str = Form(...),
    state: str = Form(""),
    db: AsyncSession = Depends(get_session),
):
    """Verify the JWT and set this app's own session cookie.

    Also upserts a row into local_users so /admin/users can show who
    has used the app.
    """
    cookie_state = request.cookies.get("sso_state", "")
    if not cookie_state or cookie_state != state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid state")

    try:
        claims = verify_sso_id_token(id_token)
    except TokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Token rejected: {e}") from e

    email = (claims["email"] or "").lower()
    now = datetime.now(timezone.utc)

    # Cache the user's Google group memberships so group-based role
    # mappings + page permissions resolve without a live API hit per page.
    group_emails = await fetch_user_group_emails(email)

    existing = (
        await db.execute(select(LocalUser).where(LocalUser.email == email))
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            LocalUser(
                email=email,
                name=claims.get("name") or email,
                is_admin=bool(claims.get("is_admin")),
                is_super_admin=bool(claims.get("is_super_admin")),
                group_emails=",".join(group_emails),
                last_seen_at=now,
            )
        )
    else:
        existing.name = claims.get("name") or existing.name
        existing.is_admin = bool(claims.get("is_admin"))
        existing.is_super_admin = bool(claims.get("is_super_admin"))
        existing.group_emails = ",".join(group_emails)
        existing.last_seen_at = now
        if not existing.is_active:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Your access to this app has been revoked locally.",
            )
    await db.commit()

    # Resolve + persist this app's role from group mappings (highest wins).
    app_role = await resolve_role_on_login(db, email, group_emails)

    request.session["user"] = {
        "sub": claims["sub"],
        "email": email,
        "name": claims.get("name") or email,
        "picture": claims.get("picture"),
        "is_admin": claims.get("is_admin", False),
        "is_super_admin": claims.get("is_super_admin", False),
        "app_role": app_role,
        "group_emails": group_emails,
    }

    resp = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    resp.delete_cookie("sso_state", path="/auth/sso")
    return resp


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
