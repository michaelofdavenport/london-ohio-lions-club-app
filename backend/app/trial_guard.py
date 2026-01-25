# backend/app/trial_guard.py
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Tuple

from fastapi import Depends, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import auth, models
from app.database import get_db

TRIAL_DAYS = 7

# Routes that must ALWAYS remain accessible even when locked
ALWAYS_ALLOWED_PREFIXES = (
    "/billing",           # checkout/portal/webhook/status
    "/member/login",      # login
    "/health",
    "/version",
    "/public",            # public request pages/APIs
    "/static",            # static assets
    "/admin/bootstrap",   # allow bootstrap without JWT
)


def _is_always_allowed(path: str) -> bool:
    return path.startswith(ALWAYS_ALLOWED_PREFIXES)


def _utcnow() -> datetime:
    return datetime.utcnow()


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).strip())
    except Exception:
        return None


def _ensure_trial_columns(db: Session) -> None:
    """
    Safe, SQLite-friendly 'migrations' for trial fields.
    """
    try:
        cols = db.execute(text("PRAGMA table_info(clubs)")).fetchall()
        existing = {c[1] for c in cols}

        if "trial_started_at" not in existing:
            db.execute(text("ALTER TABLE clubs ADD COLUMN trial_started_at DATETIME"))
            db.commit()

        if "trial_expires_at" not in existing:
            db.execute(text("ALTER TABLE clubs ADD COLUMN trial_expires_at DATETIME"))
            db.commit()
    except Exception:
        db.rollback()


def _ensure_trial_claim_table(db: Session) -> None:
    """
    Tracks emails that have ever claimed a free trial (one-time per email).
    """
    try:
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS trial_claims (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    claimed_at DATETIME NOT NULL
                )
                """
            )
        )
        db.commit()
    except Exception:
        db.rollback()


def _email_normalize(email: str) -> str:
    return (email or "").strip().lower()


def has_email_claimed_trial(db: Session, email: str) -> bool:
    email_n = _email_normalize(email)
    if not email_n:
        return False
    _ensure_trial_claim_table(db)
    row = db.execute(
        text("SELECT 1 FROM trial_claims WHERE email = :e LIMIT 1"),
        {"e": email_n},
    ).fetchone()
    return bool(row)


def claim_trial_for_email(db: Session, email: str) -> None:
    email_n = _email_normalize(email)
    if not email_n:
        return
    _ensure_trial_claim_table(db)
    try:
        db.execute(
            text("INSERT OR IGNORE INTO trial_claims(email, claimed_at) VALUES(:e, :t)"),
            {"e": email_n, "t": _utcnow().isoformat()},
        )
        db.commit()
    except Exception:
        db.rollback()


def get_trial_info(db: Session, club: models.Club) -> dict:
    """
    Returns trial status info for a club.
    """
    _ensure_trial_columns(db)

    started = _parse_dt(getattr(club, "trial_started_at", None))
    expires = _parse_dt(getattr(club, "trial_expires_at", None))

    if started and not expires:
        expires = started + timedelta(days=TRIAL_DAYS)

    now = _utcnow()

    if not started:
        return {
            "status": "never",
            "started_at": None,
            "expires_at": None,
            "days_left": 0,
            "expired": False,
        }

    expired = bool(expires and now >= expires)
    days_left = 0
    if expires and not expired:
        remaining = expires - now
        days_left = max(0, int((remaining.total_seconds() + 86399) // 86400))

    return {
        "status": "active" if not expired else "expired",
        "started_at": started.isoformat() if started else None,
        "expires_at": expires.isoformat() if expires else None,
        "days_left": int(days_left),
        "expired": bool(expired),
    }


def start_trial_if_allowed(db: Session, club: models.Club, owner_email: str) -> dict:
    """
    Starts a 7-day trial for the club IF:
      - club has not started trial yet, AND
      - owner_email has never claimed trial before (global constraint)
    """
    _ensure_trial_columns(db)

    owner_email_n = _email_normalize(owner_email)
    if not owner_email_n:
        raise HTTPException(status_code=400, detail="Missing owner email")

    existing_started = _parse_dt(getattr(club, "trial_started_at", None))
    if existing_started:
        return get_trial_info(db, club)

    if has_email_claimed_trial(db, owner_email_n):
        return {
            "status": "blocked",
            "reason": "TRIAL_ALREADY_USED_FOR_EMAIL",
            "started_at": None,
            "expires_at": None,
            "days_left": 0,
            "expired": True,
        }

    now = _utcnow()
    expires = now + timedelta(days=TRIAL_DAYS)

    try:
        club.trial_started_at = now.isoformat()
        club.trial_expires_at = expires.isoformat()
        db.commit()
    except Exception:
        db.rollback()
        raise

    claim_trial_for_email(db, owner_email_n)
    return get_trial_info(db, club)


def is_club_active_for_app(db: Session, club: models.Club) -> Tuple[bool, dict]:
    """
    Returns (allowed, info) where allowed means:
      - PRO always allowed
      - FREE allowed only if trial active
      - otherwise locked
    """
    plan = (getattr(club, "plan", "FREE") or "FREE").upper().strip()
    sub_status = (getattr(club, "subscription_status", "inactive") or "inactive").strip()

    trial = get_trial_info(db, club)

    if plan == "PRO":
        return True, {"plan": plan, "subscription_status": sub_status, "trial": trial, "locked": False}

    if trial.get("status") == "active":
        return True, {"plan": plan, "subscription_status": sub_status, "trial": trial, "locked": False}

    return False, {"plan": plan, "subscription_status": sub_status, "trial": trial, "locked": True}


def _privilege_info(member: models.Member) -> tuple[bool, str, bool, bool]:
    role = (getattr(member, "role", "") or "").upper().strip()
    is_admin = bool(getattr(member, "is_admin", False))
    is_super_admin = bool(getattr(member, "is_super_admin", False))
    is_privileged = (role == "OWNER") or is_admin or is_super_admin
    return is_privileged, role, is_admin, is_super_admin


def _enforce_access(request: Request, db: Session, member: models.Member) -> models.Member:
    """
    Core enforcement used by BOTH:
      - dependency-based guard (require_active_access)
      - middleware (TrialGuardMiddleware)
    """
    path = request.url.path

    # Always allow these paths even if locked
    if _is_always_allowed(path):
        return member

    is_privileged, _, _, _ = _privilege_info(member)

    # Never lock privileged users out of admin tools
    if path.startswith("/admin"):
        if is_privileged:
            return member
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "NOT_ADMIN", "message": "Admin access required."},
        )

    # Allow privileged users to operate the app even if locked
    if is_privileged:
        return member

    # Normal lock rules for everyone else
    club = db.get(models.Club, member.club_id)
    if not club:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "ACCESS_DENIED", "message": "Access denied (club not found)."},
        )

    allowed, info = is_club_active_for_app(db, club)
    if allowed:
        return member

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "TRIAL_EXPIRED",
            "message": "Your free trial has ended. Please upgrade to PRO to continue.",
            **info,
        },
    )


def require_active_access(
    request: Request,
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
) -> models.Member:
    """
    Dependency version (use on routers/endpoints if you want).
    """
    return _enforce_access(request, db, member)


class TrialGuardMiddleware(BaseHTTPMiddleware):
    """
    Middleware version.

    Behavior:
      - If path is ALWAYS_ALLOWED: pass-through
      - Otherwise requires JWT (via auth.get_current_member_from_request)
      - Applies the same lock rules as require_active_access
      - Returns JSON with correct HTTP status on block
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Always-allowed paths bypass everything
        if _is_always_allowed(path):
            return await call_next(request)

        # We need a DB session inside middleware
        db = next(get_db())
        try:
            # IMPORTANT:
            # Use a request-aware auth helper designed for middleware.
            # Do NOT call dependency-style get_current_member() with request=...
            try:
                member = auth.get_current_member_from_request(request, db)  # type: ignore[attr-defined]
            except AttributeError:
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={
                        "detail": {
                            "code": "AUTH_HELPER_MISSING",
                            "message": "auth.get_current_member_from_request(request, db) is missing. Add it to app/auth.py.",
                        }
                    },
                )
            except HTTPException as e:
                return JSONResponse(status_code=e.status_code, content={"detail": e.detail})

            # Enforce lock rules
            try:
                _enforce_access(request, db, member)
            except HTTPException as e:
                return JSONResponse(status_code=e.status_code, content={"detail": e.detail})

            return await call_next(request)

        finally:
            db.close()
