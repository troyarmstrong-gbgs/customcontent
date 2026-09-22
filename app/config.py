"""App configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8",
        case_sensitive=False, extra="ignore",
    )

    public_url: str = "http://localhost:8000"
    session_secret: str = "change-me"
    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/app"

    # All five SSO_* vars come from the service app's "register app" screen.
    sso_issuer: str = "https://sso.cgdata.app"
    sso_authorization_url: str = "https://sso.cgdata.app/auth/authorize"
    sso_jwks_url: str = "https://sso.cgdata.app/.well-known/jwks.json"
    sso_client_id: str = ""
    sso_client_secret: str = ""

    # The service app polls /service-app/permissions on this app with
    # this Bearer key, to maintain a unified "who has access to what"
    # view in its admin UI. Customize the endpoint to return your app's
    # users + roles — see app/routes_permissions.py.
    service_app_permissions_key: str = ""

    # The person who requested/owns this app. Set automatically at
    # bootstrap. On first sign-in they're granted admin of THIS app, so a
    # new app starts locked to its owner (deny-by-default for everyone
    # else) rather than open to the whole org.
    app_owner_email: str = ""

    # --- this app ---------------------------------------------------------

    # The kill switch for the guest-facing form. Set false to stop taking
    # submissions (the producer view keeps working) without a redeploy of
    # anything else — useful between event seasons or if the form is ever
    # abused. SSO is never affected by this.
    public_form_enabled: bool = True

    # Server-side spelling and grammar check in the producer view. Leave
    # empty to turn the feature off; the button then reports that it isn't
    # configured rather than failing. The key never reaches the browser.
    anthropic_api_key: str = ""
    spellcheck_model: str = "claude-sonnet-4-5"


@lru_cache
def get_settings() -> Settings:
    return Settings()
