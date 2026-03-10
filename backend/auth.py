import secrets
from datetime import datetime, timedelta, timezone

import jwt
import msal
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

SCOPES = ["User.Read", "Mail.Read", "Mail.ReadBasic"]
ALLOWED_DOMAIN = "orka-global.com"
_ALGORITHM = "HS256"
_SESSION_TTL_HOURS = 8
# Refresh the MS token when it has less than this many seconds left
_MS_TOKEN_REFRESH_BUFFER_SECS = 60


# Resolved at request time from settings so env changes take effect without restart
def _redirect_uri() -> str:
    return settings.redirect_uri

def _frontend_url() -> str:
    return settings.frontend_url

# Use secure cookies when not running on plain localhost (i.e. production HTTPS)
def _secure_cookies() -> bool:
    return not settings.redirect_uri.startswith("http://localhost")


# ── MSAL singleton ────────────────────────────────────────────────────────────
# A single instance is reused across all requests so its in-memory token cache
# persists between calls. This is what makes acquire_token_silent() work for
# refresh-token-based renewal without a separate token store.

_msal_instance: msal.ConfidentialClientApplication | None = None


def _msal_app() -> msal.ConfidentialClientApplication:
    global _msal_instance
    if _msal_instance is None:
        _msal_instance = msal.ConfidentialClientApplication(
            settings.microsoft_client_id,
            authority=f"https://login.microsoftonline.com/{settings.microsoft_tenant_id}",
            client_credential=settings.microsoft_client_secret,
        )
    return _msal_instance


def _check_domain(email: str) -> bool:
    return email.lower().endswith(f"@{ALLOWED_DOMAIN}")


# ── Session token helpers ─────────────────────────────────────────────────────

def _create_session_token(
    oid: str,
    email: str,
    name: str,
    ms_access_token: str,
    ms_token_exp: str,
    home_account_id: str = "",
) -> str:
    payload = {
        "sub": oid,
        "email": email,
        "name": name,
        "ms_access_token": ms_access_token,
        "ms_token_exp": ms_token_exp,           # ISO-8601 when the MS token expires
        "home_account_id": home_account_id,     # MSAL cache key for silent refresh
        "exp": datetime.now(tz=timezone.utc) + timedelta(hours=_SESSION_TTL_HOURS),
        "iat": datetime.now(tz=timezone.utc),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def _decode_session_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])


# ── Token expiry / refresh helpers ────────────────────────────────────────────

def is_ms_token_expired(user: dict) -> bool:
    """Return True if the MS access token has expired or will expire within the buffer window."""
    exp_str = user.get("ms_token_exp", "")
    if not exp_str:
        return True
    try:
        exp = datetime.fromisoformat(exp_str)
        return datetime.now(tz=timezone.utc) >= exp - timedelta(seconds=_MS_TOKEN_REFRESH_BUFFER_SECS)
    except ValueError:
        return True


def try_refresh_ms_token(home_account_id: str) -> dict | None:
    """
    Silently refresh the MS access token using MSAL's in-memory cache.

    Returns {"access_token": str, "ms_token_exp": str} on success, or None when
    the cache has no entry for this account (e.g. server restarted since login).
    Returning None means the caller must force a re-login.
    """
    if not home_account_id:
        return None

    app = _msal_app()
    accounts = app.get_accounts()
    account = next(
        (a for a in accounts if a.get("home_account_id") == home_account_id),
        None,
    )
    if account is None:
        return None  # Cache miss — server may have restarted

    result = app.acquire_token_silent(SCOPES, account=account)
    if not result or "error" in result:
        return None

    expires_in = result.get("expires_in", 3600)
    ms_token_exp = (
        datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in)
    ).isoformat()
    return {
        "access_token": result["access_token"],
        "ms_token_exp": ms_token_exp,
    }


def reissue_session_cookie(
    response: Response,
    user: dict,
    access_token: str,
    ms_token_exp: str,
) -> None:
    """Overwrite the session cookie with a freshly refreshed MS access token."""
    new_token = _create_session_token(
        oid=user["sub"],
        email=user["email"],
        name=user["name"],
        ms_access_token=access_token,
        ms_token_exp=ms_token_exp,
        home_account_id=user.get("home_account_id", ""),
    )
    response.set_cookie(
        "session",
        new_token,
        httponly=True,
        max_age=_SESSION_TTL_HOURS * 3600,
        samesite="lax",
        secure=_secure_cookies(),
    )


# ── Dependency ────────────────────────────────────────────────────────────────

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


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/login")
def login():
    """Redirect the browser to Microsoft login."""
    state = secrets.token_urlsafe(16)
    redirect_uri = _redirect_uri()
    auth_url = _msal_app().get_authorization_request_url(
        SCOPES,
        redirect_uri=redirect_uri,
        state=state,
    )
    redirect = RedirectResponse(auth_url)
    redirect.set_cookie(
        "oauth_state", state,
        httponly=True, max_age=300, samesite="lax", secure=_secure_cookies(),
    )
    return redirect


@router.get("/callback")
def callback(code: str, state: str, request: Request):
    """Exchange auth code → tokens, enforce domain, issue session cookie."""

    # CSRF guard
    expected_state = request.cookies.get("oauth_state")
    if not expected_state or expected_state != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    result = _msal_app().acquire_token_by_authorization_code(
        code,
        scopes=SCOPES,
        redirect_uri=_redirect_uri(),
    )

    if "error" in result:
        raise HTTPException(
            status_code=400,
            detail=result.get("error_description", result["error"]),
        )

    claims = result.get("id_token_claims", {})
    email = claims.get("preferred_username", "")

    # Domain restriction — only @orka-global.com accounts allowed
    if not _check_domain(email):
        redirect = RedirectResponse(url=f"{_frontend_url()}/login?error=unauthorized_domain")
        redirect.delete_cookie("oauth_state")
        return redirect

    # Calculate when the Microsoft access token expires
    expires_in_seconds = result.get("expires_in", 3600)
    ms_token_exp = (
        datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in_seconds)
    ).isoformat()

    # home_account_id lets us look up this user's tokens in the MSAL cache later
    account = result.get("account") or {}
    home_account_id = account.get("home_account_id", "")

    session_token = _create_session_token(
        oid=claims.get("oid", ""),
        email=email,
        name=claims.get("name", ""),
        ms_access_token=result.get("access_token", ""),
        ms_token_exp=ms_token_exp,
        home_account_id=home_account_id,
    )

    redirect = RedirectResponse(url=f"{_frontend_url()}/dashboard")
    redirect.delete_cookie("oauth_state")
    redirect.set_cookie(
        "session",
        session_token,
        httponly=True,
        max_age=_SESSION_TTL_HOURS * 3600,
        samesite="lax",
        secure=_secure_cookies(),
    )
    return redirect


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    """Return current user info (no sensitive tokens)."""
    return {
        "sub": current_user["sub"],
        "email": current_user["email"],
        "name": current_user["name"],
        "ms_token_exp": current_user.get("ms_token_exp"),
    }


@router.get("/logout")
def logout():
    redirect = RedirectResponse(url=_frontend_url())
    redirect.delete_cookie("session")
    return redirect
