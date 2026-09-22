"""Verify JWTs issued by the Curiosity Games service app.

This is the reference implementation. The PyJWKClient handles fetching and
caching the public keys from {SSO_JWKS_URL}; we just check the resulting
claims match what we expect.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

from app.config import get_settings


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    return PyJWKClient(get_settings().sso_jwks_url)


class TokenError(Exception):
    """Raised when a JWT fails verification."""


def verify_sso_id_token(token: str) -> dict[str, Any]:
    """Verify a JWT issued by the service app and return its claims.

    Raises TokenError on any verification failure (bad signature, wrong
    audience/issuer, expired, etc.).
    """
    s = get_settings()
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=s.sso_client_id,
            issuer=s.sso_issuer,
        )
    except jwt.exceptions.PyJWTError as e:
        raise TokenError(str(e)) from e

    if not claims.get("email_verified"):
        raise TokenError("Email not verified by the service app")

    return claims
