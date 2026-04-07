"""Authentication helpers."""

import os
import bcrypt
from fastapi import HTTPException, Request

API_TOKEN = os.environ.get("API_TOKEN", "")  # Full read-write access
API_READ_TOKEN = os.environ.get("API_READ_TOKEN", "")  # Read-only access
APP_USERNAME = os.environ.get("APP_USERNAME", "amy")
APP_PASSWORD_HASH = os.environ.get("APP_PASSWORD_HASH", "")


def verify_credentials(username: str, password: str) -> bool:
    """Verify username and bcrypt-hashed password."""
    if username != APP_USERNAME:
        return False
    if not APP_PASSWORD_HASH:
        return False
    return bcrypt.checkpw(password.encode(), APP_PASSWORD_HASH.encode())


def _extract_bearer_token(request: Request) -> str | None:
    """Extract Bearer token from Authorization header, or None."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def verify_api_token(request: Request):
    """Dependency for READ endpoints: accepts read token, write token, or session.

    Use this on all GET endpoints. Both tokens grant read access.
    """
    token = _extract_bearer_token(request)
    if token is not None:
        if token == API_TOKEN:
            return
        if API_READ_TOKEN and token == API_READ_TOKEN:
            return
        raise HTTPException(status_code=401, detail="Unauthorized")
    if require_session(request):
        return
    raise HTTPException(status_code=401, detail="Unauthorized")


def verify_write_token(request: Request):
    """Dependency for WRITE endpoints: requires write token or session.

    Use this on all POST/PUT/DELETE endpoints. The read-only token is rejected.
    """
    token = _extract_bearer_token(request)
    if token is not None:
        if token == API_TOKEN:
            return
        raise HTTPException(status_code=403, detail="Read-only token cannot modify data")
    if require_session(request):
        return
    raise HTTPException(status_code=401, detail="Unauthorized")


def require_session(request: Request):
    """Check session cookie for page routes. Returns True if authenticated."""
    return request.session.get("authenticated") is True
