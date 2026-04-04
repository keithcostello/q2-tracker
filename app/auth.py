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
    """Dependency: verify Bearer token for API routes."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = auth[7:]
    if token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


def require_session(request: Request):
    """Check session cookie for page routes. Returns True if authenticated."""
    return request.session.get("authenticated") is True
