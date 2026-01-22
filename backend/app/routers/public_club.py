# app/routers/public_club.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.database import get_db
from app import models

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/clubs")
def list_clubs(db: Session = Depends(get_db)):
    """
    Debug helper: shows what clubs are actually inside the CURRENT database.
    """
    clubs = db.execute(select(models.Club).order_by(models.Club.id.asc())).scalars().all()
    return {
        "ok": True,
        "count": len(clubs),
        "clubs": [{"id": c.id, "slug": c.slug, "name": c.name} for c in clubs],
    }


@router.get("/club/{slug}")
def get_club_by_slug(slug: str, db: Session = Depends(get_db)):
    """
    Returns public club info by slug.
    """
    s = (slug or "").strip()
    if not s:
        raise HTTPException(status_code=400, detail="Missing club slug")

    club = db.execute(select(models.Club).where(models.Club.slug == s)).scalar_one_or_none()
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")

    return {
        "ok": True,
        "club": {
            "id": club.id,
            "slug": club.slug,
            "name": club.name,
            "plan": getattr(club, "plan", "FREE"),
        },
    }
