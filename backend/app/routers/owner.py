# app/routers/owner.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.database import get_db
from app.trial_guard import require_active_access


router = APIRouter(
    prefix="/owner",
    tags=["owner"],
    dependencies=[
        Depends(auth.require_owner),       # owner required
        Depends(require_active_access),    # ✅ Phase 4 hard-lock trial gate
    ],
)


class OwnerSetAdminIn(BaseModel):
    is_admin: bool


class OwnerTransferIn(BaseModel):
    new_owner_member_id: int


class OwnerClubUpdateIn(BaseModel):
    name: Optional[str] = None
    logo_url: Optional[str] = None
    is_active: Optional[bool] = None


def _must_be_same_club(owner: models.Member, target: models.Member) -> None:
    if (target.club_id is None) or (owner.club_id != target.club_id):
        raise HTTPException(status_code=404, detail="Member not found")


@router.patch("/members/{member_id}/admin", response_model=schemas.MemberOut)
def owner_set_member_admin(
    member_id: int,
    payload: OwnerSetAdminIn,
    db: Session = Depends(get_db),
    owner: models.Member = Depends(auth.require_owner),
):
    m = db.get(models.Member, member_id)
    if not m:
        raise HTTPException(status_code=404, detail="Member not found")

    _must_be_same_club(owner, m)

    if m.id == owner.id and payload.is_admin is False:
        raise HTTPException(status_code=400, detail="Owner cannot remove their own admin flag")

    m.is_admin = bool(payload.is_admin)

    if getattr(m, "role", "MEMBER") != auth.ROLE_OWNER:
        m.role = auth.ROLE_ADMIN if m.is_admin else auth.ROLE_MEMBER

    db.commit()
    db.refresh(m)
    return m


@router.post("/transfer", response_model=dict)
def owner_transfer_ownership(
    payload: OwnerTransferIn,
    db: Session = Depends(get_db),
    owner: models.Member = Depends(auth.require_owner),
):
    if int(payload.new_owner_member_id) == owner.id:
        raise HTTPException(status_code=400, detail="You are already the owner")

    new_owner = db.get(models.Member, int(payload.new_owner_member_id))
    if not new_owner:
        raise HTTPException(status_code=404, detail="Member not found")

    _must_be_same_club(owner, new_owner)

    new_owner.role = auth.ROLE_OWNER
    new_owner.is_admin = True

    owner.role = auth.ROLE_ADMIN
    owner.is_admin = True

    db.commit()
    return {"ok": True, "new_owner_member_id": new_owner.id, "club_id": owner.club_id}


@router.patch("/club", response_model=dict)
def owner_update_club(
    payload: OwnerClubUpdateIn,
    db: Session = Depends(get_db),
    owner: models.Member = Depends(auth.require_owner),
):
    club = db.get(models.Club, owner.club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")

    if payload.name is not None:
        club.name = payload.name.strip() or club.name
    if payload.logo_url is not None:
        club.logo_url = payload.logo_url.strip() or None
    if payload.is_active is not None:
        club.is_active = bool(payload.is_active)

    db.commit()
    db.refresh(club)

    return {
        "ok": True,
        "club": {
            "id": club.id,
            "slug": club.slug,
            "name": club.name,
            "logo_url": club.logo_url,
            "is_active": club.is_active,
        },
    }
