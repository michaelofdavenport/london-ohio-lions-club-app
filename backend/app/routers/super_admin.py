# app/routers/super_admin.py
from __future__ import annotations

import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth, models
from app.database import get_db
from app.trial_guard import require_active_access


router = APIRouter(
    prefix="/super",
    tags=["super"],
    dependencies=[
        Depends(auth.require_super_admin),  # super-admin required
        Depends(require_active_access),     # ✅ Phase 4 hard-lock trial gate
    ],
)


class SuperCreateClubIn(BaseModel):
    slug: str
    name: str
    owner_email: str
    owner_full_name: Optional[str] = None
    owner_temp_password: Optional[str] = None
    logo_url: Optional[str] = None


def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    out = []
    for ch in s:
        if ch.isalnum() or ch in ("-", "_"):
            out.append(ch)
        elif ch in (" ", ".", "/"):
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "club"


def _random_temp_password() -> str:
    return "Temp-" + secrets.token_urlsafe(12)


@router.post("/onboard/club", response_model=dict, status_code=201)
def super_onboard_club(
    payload: SuperCreateClubIn,
    db: Session = Depends(get_db),
    super_admin: models.Member = Depends(auth.require_super_admin),
):
    slug = _slugify(payload.slug)
    if not slug:
        raise HTTPException(status_code=400, detail="Missing slug")

    if db.scalar(select(models.Club).where(models.Club.slug == slug)):
        raise HTTPException(status_code=400, detail="Club slug already exists")

    owner_email = (payload.owner_email or "").strip().lower()
    if not owner_email:
        raise HTTPException(status_code=400, detail="Missing owner_email")

    if db.scalar(select(models.Member).where(models.Member.email == owner_email)):
        raise HTTPException(status_code=400, detail="Owner email already exists")

    club = models.Club(
        slug=slug,
        name=(payload.name or "").strip() or slug,
        logo_url=(payload.logo_url or "").strip() or "/static/images/lions_emblem.png",
        is_active=True,
    )
    db.add(club)
    db.commit()
    db.refresh(club)

    temp_password = (payload.owner_temp_password or "").strip() or _random_temp_password()

    owner = models.Member(
        email=owner_email,
        hashed_password=auth.hash_password(temp_password),
        full_name=(payload.owner_full_name or "").strip() or "Club Owner",
        is_admin=True,
        is_active=True,
        club_id=club.id,
        role=auth.ROLE_OWNER,
        is_super_admin=False,
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

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
            "temp_password": temp_password,
        },
        "links": {
            "public_info": f"/public/{club.slug}/info",
            "public_request": f"/public/{club.slug}/request",
            "admin_tools": "/admin/tools",
            "login_page": "/static/index.html",
        },
    }
