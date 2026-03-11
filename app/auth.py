from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer
from app.config import get_settings

settings = get_settings()
serializer = URLSafeTimedSerializer(settings.APP_SECRET_KEY)

SESSION_COOKIE = "admin_session"
SESSION_MAX_AGE = 86400  # 24 hours


def create_session_token(username: str) -> str:
    return serializer.dumps({"username": username})


def verify_session_token(token: str) -> dict | None:
    try:
        return serializer.loads(token, max_age=SESSION_MAX_AGE)
    except Exception:
        return None


def require_auth(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    data = verify_session_token(token)
    if not data:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return data


def auth_redirect_if_needed(request: Request) -> RedirectResponse | None:
    """For use in template routes where we want redirect instead of exception."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return RedirectResponse(url="/login", status_code=303)
    data = verify_session_token(token)
    if not data:
        return RedirectResponse(url="/login", status_code=303)
    return None
