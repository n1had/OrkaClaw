import secrets
from datetime import datetime, timedelta, timezone

import jwt
import msal
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

SCOPES = ["User.Read", "Mail.Read", "Mail.ReadBasic"]
_ALGORITHM = "HS256"
_SESSION_TTL_HOURS = 8
# Override via env var REDIRECT_URI if needed
REDIRECT_URI = "http://localhost:8000/auth/callback"
FRONTEND_URL = "http://localhost:5173"


def _msal_app() -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        settings.microsoft_client_id,
        authority=f"https://login.microsoftonline.com/{settings.microsoft_tenant_id}",
        client_credential=settings.microsoft_client_secret,
    )


def _create_session_token(
    oid: str, email: str, name: str, ms_access_token: str
) -> str:
    payload = {
        "sub": oid,
        "email": email,
        "name": name,
        "ms_access_token": ms_access_token,
        "exp": datetime.now(tz=timezone.utc) + timedelta(hours=_SESSION_TTL_HOURS),
        "iat": datetime.now(tz=timezone.utc),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def _decode_session_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])


# ── Dependency ──────────────────────────────────────────────────────────────


def get_current_user(request: Request) -> dict:
    """FastAPI dependency — returns decoded JWT payload or raises 401."""
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return _decode_session_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid session")


# ── Routes ──────────────────────────────────────────────────────────────────


@router.get("/login")
def login(response: Response):
    """Redirect the browser to Microsoft login."""
    state = secrets.token_urlsafe(16)
    auth_url = _msal_app().get_authorization_request_url(
        SCOPES,
        redirect_uri=REDIRECT_URI,
        state=state,
    )
    redirect = RedirectResponse(auth_url)
    # Store state in a short-lived cookie to validate on callback (CSRF guard)
    redirect.set_cookie("oauth_state", state, httponly=True, max_age=300, samesite="lax")
    return redirect


@router.get("/callback")
def callback(code: str, state: str, request: Request):
    """Exchange auth code for tokens, issue a session cookie."""
    # CSRF check
    expected_state = request.cookies.get("oauth_state")
    if not expected_state or expected_state != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    result = _msal_app().acquire_token_by_authorization_code(
        code,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )

    if "error" in result:
        raise HTTPException(
            status_code=400,
            detail=result.get("error_description", result["error"]),
        )

    claims = result.get("id_token_claims", {})
    session_token = _create_session_token(
        oid=claims.get("oid", ""),
        email=claims.get("preferred_username", ""),
        name=claims.get("name", ""),
        ms_access_token=result.get("access_token", ""),
    )

    redirect = RedirectResponse(url=f"{FRONTEND_URL}/dashboard")
    redirect.delete_cookie("oauth_state")
    redirect.set_cookie(
        "session",
        session_token,
        httponly=True,
        max_age=_SESSION_TTL_HOURS * 3600,
        samesite="lax",
    )
    return redirect


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    """Return current user info (no sensitive tokens)."""
    return {
        "sub": current_user["sub"],
        "email": current_user["email"],
        "name": current_user["name"],
    }


@router.get("/logout")
def logout():
    redirect = RedirectResponse(url=FRONTEND_URL)
    redirect.delete_cookie("session")
    return redirect
