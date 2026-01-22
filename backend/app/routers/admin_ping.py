# app/routers/admin_ping.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from app import auth, models

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)

@router.get("/ping")
def admin_ping(me: models.Member = Depends(auth.get_current_member)):
    """
    Frontend guard calls this to decide if Admin Tools are allowed.
    MUST work even if trial is expired.
    """
    role = (getattr(me, "role", "") or "").upper().strip()
    is_admin = bool(getattr(me, "is_admin", False))
    is_super_admin = bool(getattr(me, "is_super_admin", False))

    if not (role == "OWNER" or is_admin or is_super_admin):
        raise HTTPException(status_code=403, detail="Not an admin")

    return {
        "ok": True,
        "role": "OWNER" if role == "OWNER" else "ADMIN",
        "is_admin": is_admin,
        "is_super_admin": is_super_admin,
    }
