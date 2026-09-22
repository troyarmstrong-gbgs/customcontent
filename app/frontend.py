"""Serve the single-page front end with its server-supplied context.

The same document backs both the public form and the producer view. What
it renders is decided by the `mode` injected here — and, more to the
point, by which API calls the server is willing to answer. The injected
flags are a UI hint; `routes_review.py` is the access control.

The file is read once per process and cached with an ETag so a browser
revalidates instead of re-downloading ~100 KB on every navigation.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

INDEX = Path(__file__).parent / "frontend" / "index.html"
PLACEHOLDER = "<!--APP_CONTEXT-->"


@lru_cache(maxsize=1)
def _template() -> str:
    return INDEX.read_text(encoding="utf-8")


def render_page(context: dict) -> str:
    """Return the page with `window.__APP__` set for this request."""
    # </script> inside JSON would end the tag early; escaping the slash is
    # the standard defence and stays valid JSON.
    blob = json.dumps(context, ensure_ascii=False).replace("</", "<\\/")
    tag = f"<script>window.__APP__ = {blob};</script>"
    return _template().replace(PLACEHOLDER, tag, 1)


def page_etag(context: dict) -> str:
    return '"%s"' % hashlib.sha256(
        (render_page(context)).encode("utf-8")
    ).hexdigest()[:32]
