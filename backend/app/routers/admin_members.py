# app/routers/admin_members.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.database import get_db
from app.trial_guard import require_active_access


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[
        Depends(auth.require_admin),       # admin required
        Depends(require_active_access),    # ✅ Phase 4 hard-lock trial gate
    ],
)


def _is_super_admin(member_obj: models.Member) -> bool:
    return bool(getattr(member_obj, "is_super_admin", False))


@router.get("/members", response_model=list[schemas.MemberOut])
def admin_list_members(
    db: Session = Depends(get_db),
    admin: models.Member = Depends(auth.require_admin),
):
    stmt = select(models.Member)

    if not _is_super_admin(admin):
        stmt = stmt.where(models.Member.club_id == admin.club_id)

    stmt = stmt.order_by(func.coalesce(models.Member.full_name, "ZZZ"), models.Member.email)
    return db.scalars(stmt).all()


@router.post("/members", response_model=schemas.MemberOut, status_code=201)
def admin_create_member(
    payload: schemas.MemberCreateIn,
    db: Session = Depends(get_db),
    admin: models.Member = Depends(auth.require_admin),
):
    if db.scalar(select(models.Member).where(models.Member.email == payload.email)):
        raise HTTPException(status_code=400, detail="Email already exists")

    new_member = models.Member(
        email=payload.email,
        hashed_password=auth.hash_password(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
        address=payload.address,
        member_since=payload.member_since,
        birthday=payload.birthday,
        is_admin=payload.is_admin,
        is_active=True,
        club_id=admin.club_id,
        role=("ADMIN" if payload.is_admin else "MEMBER"),
    )
    db.add(new_member)
    db.commit()
    db.refresh(new_member)
    return new_member


@router.patch("/members/{member_id}", response_model=schemas.MemberOut)
def admin_update_member(
    member_id: int,
    payload: schemas.AdminMemberUpdateIn,
    db: Session = Depends(get_db),
    admin: models.Member = Depends(auth.require_admin),
):
    m = db.get(models.Member, member_id)
    if not m:
        raise HTTPException(status_code=404, detail="Member not found")

    if (not _is_super_admin(admin)) and (m.club_id != admin.club_id):
        raise HTTPException(status_code=404, detail="Member not found")

    if m.id == admin.id and payload.is_admin is False:
        raise HTTPException(status_code=400, detail="You cannot remove your own admin role")

    if payload.full_name is not None:
        m.full_name = payload.full_name
    if payload.phone is not None:
        m.phone = payload.phone
    if payload.address is not None:
        m.address = payload.address
    if payload.member_since is not None:
        m.member_since = payload.member_since
    if payload.birthday is not None:
        m.birthday = payload.birthday
    if payload.is_admin is not None:
        m.is_admin = payload.is_admin
        if getattr(m, "role", "MEMBER") != "OWNER":
            m.role = "ADMIN" if payload.is_admin else "MEMBER"

    db.commit()
    db.refresh(m)
    return m


@router.patch("/members/{member_id}/active", response_model=schemas.MemberOut)
def admin_set_member_active(
    member_id: int,
    payload: schemas.AdminMemberActiveIn,
    db: Session = Depends(get_db),
    admin: models.Member = Depends(auth.require_admin),
):
    m = db.get(models.Member, member_id)
    if not m:
        raise HTTPException(status_code=404, detail="Member not found")

    if (not _is_super_admin(admin)) and (m.club_id != admin.club_id):
        raise HTTPException(status_code=404, detail="Member not found")

    if m.id == admin.id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

    m.is_active = payload.is_active
    db.commit()
    db.refresh(m)
    return m


@router.patch("/members/{member_id}/password", status_code=200)
def admin_reset_member_password(
    member_id: int,
    payload: schemas.AdminPasswordResetIn,
    db: Session = Depends(get_db),
    admin: models.Member = Depends(auth.require_admin),
):
    m = db.get(models.Member, member_id)
    if not m:
        raise HTTPException(status_code=404, detail="Member not found")

    if (not _is_super_admin(admin)) and (m.club_id != admin.club_id):
        raise HTTPException(status_code=404, detail="Member not found")

    m.hashed_password = auth.hash_password(payload.password)
    db.commit()
    return {"ok": True}
