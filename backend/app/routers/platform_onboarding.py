# app/routers/platform_onboarding.py
from __future__ import annotations

import secrets
import string
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/platform", tags=["platform"])


def _rand_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits
    # avoid punctuation to prevent URL/clipboard weirdness
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    out = []
    prev_dash = False
    for ch in s:
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        else:
            if not prev_dash:
                out.append("-")
                prev_dash = True
    slug = "".join(out).strip("-")
    return slug


class OnboardClubIn(BaseModel):
    club_name: str
    club_slug: Optional[str] = None
    logo_url: Optional[str] = None

    owner_email: EmailStr
    owner_full_name: Optional[str] = None
    temp_password: Optional[str] = None

    @field_validator("club_name")
    @classmethod
    def _club_name_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("club_name is required")
        return v

    @field_validator("club_slug")
    @classmethod
    def _club_slug_clean(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = _slugify(v)
        return v or None

    @field_validator("logo_url")
    @classmethod
    def _logo_url_trim(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = (v or "").strip()
        return v or None

    @field_validator("temp_password")
    @classmethod
    def _pwd_min(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = (v or "").strip()
        if v and len(v) < 8:
            raise ValueError("temp_password must be at least 8 characters")
        return v or None


@router.post("/onboard")
def platform_onboard_club(
    payload: OnboardClubIn,
    db: Session = Depends(get_db),
    super_admin: models.Member = Depends(auth.require_super_admin),
):
    """
    One-click club onboarding (SUPER ADMIN ONLY):
      - Create Club
      - Create first OWNER user in that club
      - Return credentials + useful URLs
    """
    # slug: use provided or derive from name
    slug = payload.club_slug or _slugify(payload.club_name)
    if not slug:
        raise HTTPException(status_code=400, detail="Unable to create club_slug")

    # check club slug unique
    existing_club = db.scalar(select(models.Club).where(models.Club.slug == slug))
    if existing_club:
        raise HTTPException(status_code=400, detail="club_slug already exists")

    # check email unique (your model enforces global unique)
    owner_email = str(payload.owner_email).strip().lower()
    existing_member = db.scalar(select(models.Member).where(models.Member.email == owner_email))
    if existing_member:
        raise HTTPException(status_code=400, detail="owner_email already exists")

    # create club
    club = models.Club(
        slug=slug,
        name=payload.club_name.strip(),
        logo_url=payload.logo_url or None,
        is_active=True,
    )
    db.add(club)
    db.commit()
    db.refresh(club)

    # password
    pwd = payload.temp_password or _rand_password()

    # create owner
    owner = models.Member(
        club_id=club.id,
        email=owner_email,
        hashed_password=auth.hash_password(pwd),
        full_name=(payload.owner_full_name or "").strip() or "Club Owner",
        is_active=True,
        is_admin=True,                 # keep legacy in sync
        role=auth.ROLE_OWNER,          # hard role
        is_super_admin=False,          # owner of club, not platform
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    # return useful links (no external hostname assumption)
    return {
        "ok": True,
        "club": {
            "id": club.id,
            "slug": club.slug,
            "name": club.name,
            "logo_url": club.logo_url,
            "is_active": club.is_active,
        },
        "owner": {
            "id": owner.id,
            "email": owner.email,
            "full_name": owner.full_name,
            "role": owner.role,
        },
        "temp_password": pwd,
        "suggested_login": "/static/index.html",
        "public_form_info": f"/public/{club.slug}/info",
        "public_form_submit": f"/public/{club.slug}/request",
        "admin_tools": "/admin/tools",
    }
