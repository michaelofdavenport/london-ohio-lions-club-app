# app/routers/billing_status.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import auth, models

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/status")
def billing_status(
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    """
    Returns the club billing status for ANY logged-in member.

    This does not reveal Stripe secrets.
    It only tells the user if the club is PRO or FREE and basic subscription status.
    """
    club = db.get(models.Club, member.club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")

    return {
        "ok": True,
        "club": {
            "id": club.id,
            "name": club.name,
            "slug": club.slug,
            "plan": getattr(club, "plan", "FREE"),
            "subscription_status": getattr(club, "subscription_status", "inactive"),
            "current_period_end": (
                club.current_period_end.isoformat()
                if getattr(club, "current_period_end", None)
                else None
            ),
        },
    }
