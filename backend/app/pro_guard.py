# app/pro_guard.py
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import auth, models
from app.database import get_db
from app.feature_flags import TRIAL_DAYS, is_always_allowed


# -------------------------------------------------
# Trial table (Option B)
# -------------------------------------------------
TRIAL_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS trial_redemptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_normalized TEXT NOT NULL UNIQUE,
    redeemed_at DATETIME NOT NULL
);
"""


def ensure_trial_table(db: Session) -> None:
    """Safe to call repeatedly; creates table if missing."""
    try:
        db.execute(text(TRIAL_TABLE_SQL))
        db.commit()
    except Exception:
        db.rollback()


def normalize_email(email: str) -> str:
    """
    Normalizes email for one-time trial enforcement.

    - lowercases
    - trims spaces
    - Gmail-specific: strips '+' tag and '.' in local-part
      (prevents endless trials via mike+1@gmail.com and dot tricks)
    """
    e = (email or "").strip().lower()
    if not e or "@" not in e:
        return e

    local, domain = e.split("@", 1)
    domain = domain.strip()

    if domain in ("gmail.com", "googlemail.com"):
        # strip +tag
        if "+" in local:
            local = local.split("+", 1)[0]
        # remove dots
        local = local.replace(".", "")
        domain = "gmail.com"

    return f"{local}@{domain}"


def get_trial_redeemed_at(db: Session, email_normalized: str) -> Optional[datetime]:
    row = db.execute(
        text("SELECT redeemed_at FROM trial_redemptions WHERE email_normalized = :e"),
        {"e": email_normalized},
    ).fetchone()
    if not row:
        return None
    # sqlite returns str or datetime depending on driver; coerce safely
    val = row[0]
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except Exception:
        return None


def redeem_trial_once(db: Session, email_normalized: str) -> datetime:
    """
    Creates a redemption if none exists.
    If another request races, UNIQUE constraint will protect and we re-read.
    """
    now = datetime.utcnow()
    try:
        db.execute(
            text(
                "INSERT INTO trial_redemptions (email_normalized, redeemed_at) VALUES (:e, :t)"
            ),
            {"e": email_normalized, "t": now.isoformat()},
        )
        db.commit()
        return now
    except Exception:
        db.rollback()
        existing = get_trial_redeemed_at(db, email_normalized)
        return existing or now


def is_trial_active(redeemed_at: datetime) -> bool:
    return datetime.utcnow() < (redeemed_at + timedelta(days=TRIAL_DAYS))


# -------------------------------------------------
# Guards
# -------------------------------------------------
def require_member(
    member: models.Member = Depends(auth.get_current_member),
) -> models.Member:
    """Requires a logged-in member (any plan)."""
    return member


def require_access(
    request: Request,
    db: Session = Depends(get_db),
    member: models.Member = Depends(require_member),
) -> models.Member:
    """
    HARD LOCK gate (Phase 4):
    - If path is ALWAYS_ALLOWED -> allow
    - If club is PRO (and subscription active/trialing) -> allow
    - Else if trial is active (one-time per email) -> allow
    - Else -> block (trial ended / no trial)

    Apply this as a dependency to any router you want hard-locked after trial ends.
    """
    path = request.url.path

    # 1) Always-allowed (billing/login/public/static/etc.)
    if is_always_allowed(path):
        return member

    # 2) Ensure trial table exists (safe)
    ensure_trial_table(db)

    # 3) PRO check
    club = db.get(models.Club, member.club_id)
    if not club:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "ACCESS_DENIED", "message": "Access denied (club not found)."},
        )

    plan = (getattr(club, "plan", "FREE") or "FREE").upper().strip()
    sub_status = (getattr(club, "subscription_status", "inactive") or "inactive").lower().strip()

    # Treat these as "paid enough to use the product"
    pro_ok = (plan == "PRO") and (sub_status in ("active", "trialing"))
    if pro_ok:
        return member

    # 4) Trial check (one-time per email)
    email_norm = normalize_email(member.email)
    redeemed_at = get_trial_redeemed_at(db, email_norm)

    if redeemed_at is None:
        # First time this email ever hits locked content => start trial
        redeemed_at = redeem_trial_once(db, email_norm)

    if redeemed_at and is_trial_active(redeemed_at):
        return member

    # 5) Trial ended / not PRO => hard lock
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "code": "PAYMENT_REQUIRED",
            "message": "Your free trial has ended. Please upgrade to PRO to continue.",
            "plan": plan,
            "subscription_status": sub_status,
            "trial_days": TRIAL_DAYS,
            "trial_redeemed_at": redeemed_at.isoformat() if redeemed_at else None,
        },
    )


def require_pro_club(
    request: Request,
    db: Session = Depends(get_db),
    member: models.Member = Depends(require_member),
) -> models.Member:
    """
    PRO-only gate (legacy-compatible):
    - Only blocks if not PRO, but DOES allow active trial users.
    Use this for 'premium feature pages' if you *don't* want a full hard-lock.
    """
    path = request.url.path
    if is_always_allowed(path):
        return member

    ensure_trial_table(db)

    club = db.get(models.Club, member.club_id)
    if not club:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "ACCESS_DENIED", "message": "Access denied (club not found)."},
        )

    plan = (getattr(club, "plan", "FREE") or "FREE").upper().strip()
    sub_status = (getattr(club, "subscription_status", "inactive") or "inactive").lower().strip()

    # PRO wins
    if (plan == "PRO") and (sub_status in ("active", "trialing")):
        return member

    # Trial can access PRO routes during trial window
    email_norm = normalize_email(member.email)
    redeemed_at = get_trial_redeemed_at(db, email_norm)
    if redeemed_at is None:
        redeemed_at = redeem_trial_once(db, email_norm)

    if redeemed_at and is_trial_active(redeemed_at):
        return member

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "PRO_REQUIRED",
            "message": "This feature requires PRO (trial ended or not eligible).",
            "plan": plan,
            "subscription_status": sub_status,
        },
    )
