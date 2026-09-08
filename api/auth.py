"""
API-key auth for /api/* routes. Disabled by default (no API_KEY env var set)
so local/demo use (RUN_DEMO.cmd, grading, a career-fair laptop) works with
zero setup -- set API_KEY to require it. This is a real, tested access
control, not a stub; see SECURITY.md for what it is and isn't a substitute
for (real user auth/OAuth for anything beyond a single shared demo key).
"""
import os

from fastapi import Header, HTTPException


def get_configured_key() -> str | None:
    return os.environ.get("API_KEY") or None


async def require_api_key(x_api_key: str | None = Header(default=None)):
    configured = get_configured_key()
    if configured is None:
        return  # auth disabled
    if x_api_key != configured:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header")
