"""Authentication helpers."""

import os
from fastapi import HTTPException, Request

API_TOKEN = os.environ.get("API_TOKEN", "")


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
