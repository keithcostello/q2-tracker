"""Authentication helpers."""

import os
import bcrypt
from fastapi import HTTPException, Request

API_TOKEN = os.environ.get("API_TOKEN", "")
APP_USERNAME = os.environ.get("APP_USERNAME", "amy")
APP_PASSWORD_HASH = os.environ.get("APP_PASSWORD_HASH", "")


def verify_credentials(username: str, password: str) -> bool:
    """Verify username and bcrypt-hashed password."""
    if username != APP_USERNAME:
        return False
    if not APP_PASSWORD_HASH:
        return False
    return bcrypt.checkpw(password.encode(), APP_PASSWORD_HASH.encode())


def verify_api_token(request: Request):
    """Dependency: verify Bearer token or session cookie for API routes."""
    # Accept Bearer token (API clients, tracker pages)
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        if token == API_TOKEN:
            return
        raise HTTPException(status_code=401, detail="Unauthorized")
    # Accept session cookie (browser-based PWA auth)
    if require_session(request):
        return
    raise HTTPException(status_code=401, detail="Unauthorized")


def require_session(request: Request):
    """Check session cookie for page routes. Returns True if authenticated."""
    return request.session.get("authenticated") is True
