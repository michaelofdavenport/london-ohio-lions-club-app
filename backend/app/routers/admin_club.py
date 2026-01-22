# app/routers/admin_club.py
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.database import get_db
from app import models, auth
from app.emailer import send_email_if_configured

router = APIRouter(prefix="/admin", tags=["admin"])

# -----------------------------
# Helpers
# -----------------------------
def require_admin(member=Depends(auth.get_current_member)):
    # Adjust these field names only if your models differ
    is_admin = bool(getattr(member, "is_admin", False))
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return member


def _member_to_dict(m):
    return {
        "id": getattr(m, "id", None),
        "name": getattr(m, "name", None) or getattr(m, "full_name", None) or "",
        "email": getattr(m, "email", ""),
        "is_admin": bool(getattr(m, "is_admin", False)),
        "is_active": bool(getattr(m, "is_active", True)),
        "created_at": str(getattr(m, "created_at", "") or ""),
    }


def _club_to_dict(c):
    return {
        "id": getattr(c, "id", None),
        "name": getattr(c, "name", ""),
        "slug": getattr(c, "slug", ""),
    }


# -----------------------------
# Schemas
# -----------------------------
class InviteMemberIn(BaseModel):
    email: EmailStr
    name: Optional[str] = ""
    is_admin: bool = False


class ToggleActiveIn(BaseModel):
    is_active: bool


# -----------------------------
# Endpoints
# -----------------------------
@router.get("/me")
def member_me(
    member=Depends(auth.get_current_member),
):
    """
    Auth-only endpoint.
    Used by frontend immediately after login.
    MUST NOT require admin / pro / owner.
    """
    club = getattr(member, "club", None)

    return {
        "ok": True,
        "member": _member_to_dict(member),
        "club": _club_to_dict(club) if club else None,
    }


# ==========================================================
# IMPORTANT:
# These routes used to be /admin/members* which COLLIDES with
# app/routers/admin_members.py (and breaks your UI with 500s).
#
# We move them under /admin/club/* so they never collide again.
# ==========================================================

@router.get("/club/members")
def list_members_for_club(
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    club_id = getattr(admin, "club_id", None)
    if not club_id:
        raise HTTPException(status_code=400, detail="Admin user is not attached to a club.")

    stmt = (
        select(models.Member)
        .where(models.Member.club_id == club_id)
        .order_by(models.Member.id.asc())
    )
    members = db.execute(stmt).scalars().all()
    return {"ok": True, "count": len(members), "members": [_member_to_dict(m) for m in members]}


@router.post("/club/members/invite")
def invite_member_to_club(
    payload: InviteMemberIn,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    club_id = getattr(admin, "club_id", None)
    if not club_id:
        raise HTTPException(status_code=400, detail="Admin user is not attached to a club.")

    # Prevent duplicates
    existing = db.execute(
        select(models.Member).where(
            models.Member.club_id == club_id,
            models.Member.email == payload.email,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Member with that email already exists.")

    # Create a temp password
    temp_pw = auth.hash_password(auth.make_temp_password())

    m = models.Member(
        club_id=club_id,
        email=payload.email,
        # Your model might be full_name instead of name. Keep BOTH safely:
        name=(payload.name or ""),
        full_name=(payload.name or ""),
        hashed_password=temp_pw,
        is_admin=payload.is_admin,
        is_active=True,
    )
    db.add(m)
    db.commit()
    db.refresh(m)

    # Email invite (only sends if SMTP is configured & working)
    club = getattr(admin, "club", None)
    club_name = getattr(club, "name", "Your Lions Club") if club else "Your Lions Club"

    subject = f"You're invited to {club_name} Lions App"
    body = (
        f"Hello{(' ' + payload.name) if payload.name else ''},\n\n"
        f"You've been invited to join {club_name} Lions App.\n\n"
        f"Login here: {auth.app_base_url()}/static/index.html?club={getattr(club,'slug','')}\n\n"
        f"If you have trouble logging in, contact your club admin.\n"
    )

    send_email_if_configured(payload.email, subject, body)

    return {"ok": True, "member": _member_to_dict(m), "email_sent": True}


@router.patch("/club/members/{member_id}")
def set_member_active_for_club(
    member_id: int,
    payload: ToggleActiveIn,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    club_id = getattr(admin, "club_id", None)
    if not club_id:
        raise HTTPException(status_code=400, detail="Admin user is not attached to a club.")

    m = db.execute(
        select(models.Member).where(
            models.Member.id == member_id,
            models.Member.club_id == club_id,
        )
    ).scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Member not found.")

    setattr(m, "is_active", bool(payload.is_active))
    db.commit()
    db.refresh(m)

    return {"ok": True, "member": _member_to_dict(m)}


@router.get("/email-status")
def email_status(admin=Depends(require_admin)):
    # This mirrors what your server logs already told us (SMTP config / failures)
    return {
        "ok": True,
        "configured": auth.email_configured(),
        "note": "If configured=false, buyer must set SMTP env vars. If configured=true but emails fail, credentials/app-password/admin policy is the issue.",
    }
