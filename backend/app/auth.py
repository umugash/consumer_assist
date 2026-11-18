"""Server-side Supabase session verification and case ownership checks."""

import json
import time
import urllib.request
import urllib.error
from typing import Dict, Tuple

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Case

# token -> (expires_at, user). shortcut: per-instance memory cache, fine for serverless.
_CACHE: Dict[str, Tuple[float, dict]] = {}


def _supabase() -> Tuple[str, str]:
    url = (settings.SUPABASE_URL or settings.VITE_SUPABASE_URL).rstrip("/")
    key = settings.SUPABASE_KEY or settings.VITE_SUPABASE_ANON_KEY
    return url, key


def current_user(authorization: str = Header(default="")) -> dict:
    """Validate the bearer token with Supabase Auth and return {id, email}."""
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in required")
    token = authorization[7:].strip()
    hit = _CACHE.get(token)
    if hit and hit[0] > time.time():
        return hit[1]
    url, key = _supabase()
    if not url or not key:
        raise HTTPException(status_code=503, detail="Authentication is not configured on the server")
    req = urllib.request.Request(f"{url}/auth/v1/user", headers={"apikey": key, "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise HTTPException(status_code=401, detail="Session expired, please sign in again")
        raise HTTPException(status_code=503, detail="Authentication service unavailable")
    except Exception:
        raise HTTPException(status_code=503, detail="Authentication service unavailable")
    if not data.get("id"):
        raise HTTPException(status_code=401, detail="Invalid session")
    user = {"id": data["id"], "email": data.get("email")}
    if len(_CACHE) > 1000:
        _CACHE.clear()
    _CACHE[token] = (time.time() + 300, user)
    return user


def owned_case(case_id: str, user: dict = Depends(current_user), db: Session = Depends(get_db)) -> Case:
    """Load a case only if it belongs to the signed-in user (404 otherwise, to avoid ID probing)."""
    case = db.query(Case).filter(Case.id == case_id, Case.user_id == user["id"]).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case
