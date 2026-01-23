# backend/app/bootstrap.py
from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy import text, select
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, auth

router = APIRouter()


def _env(name: str) -> Optional[str]:
    v = os.getenv(name)
    return v.strip() if v else None


def _require_env(name: str) -> str:
    v = _env(name)
    if not v:
        raise HTTPException(status_code=500, detail=f"Missing required env var: {name}")
    return v


@router.post("/admin/bootstrap")
def bootstrap_first_owner(
    key: str = Query(..., description="Bootstrap key"),
    db: Session = Depends(get_db),
):
    """
    One-time bootstrap (for brand new clubs / brand new databases):
      - Requires BOOTSTRAP_KEY match
      - Creates the club (slug) if missing
      - Creates the OWNER member if missing
      - Writes a DB flag so it cannot be run again
    After success:
      - REMOVE BOOTSTRAP_* env vars in Render
    """

    # 0) Verify key matches BOOTSTRAP_KEY
    bootstrap_key = _require_env("BOOTSTRAP_KEY")
    if not secrets.compare_digest(key, bootstrap_key):
        raise HTTPException(status_code=401, detail="Invalid bootstrap key")

    # 1) Ensure the system_flags table exists (safe every run)
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS system_flags (
                key TEXT PRIMARY KEY,
                value TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )

    # 2) Hard-disable after first successful run
    used = db.execute(text("SELECT value FROM system_flags WHERE key='bootstrap_used'")).first()
    if used and used[0] == "1":
        raise HTTPException(status_code=403, detail="Bootstrap already used")

    # 3) Read env vars (BOOTSTRAP_CLUB_CODE is treated as the club SLUG)
    club_slug = _require_env("BOOTSTRAP_CLUB_CODE").strip()
    club_name = (_env("BOOTSTRAP_CLUB_NAME") or club_slug).strip()
    owner_email = _require_env("BOOTSTRAP_EMAIL").strip().lower()
    owner_password = _require_env("BOOTSTRAP_PASSWORD")

    # 4) Ensure club exists (your app uses clubs.slug)
    club = db.scalar(select(models.Club).where(models.Club.slug == club_slug))
    if not club:
        club = models.Club(
            slug=club_slug,
            name=club_name,
            logo_url="/static/images/lions_emblem.png",
            is_active=True,
        )
        db.add(club)
        db.commit()
        db.refresh(club)

    # 5) Ensure OWNER member exists (club-scoped)
    member = db.scalar(
        select(models.Member).where(
            models.Member.club_id == club.id,
            models.Member.email == owner_email,
        )
    )

    hashed = auth.hash_password(owner_password)

    if member:
        # Update password + elevate role to OWNER
        member.hashed_password = hashed
        member.is_active = True
        member.is_admin = True
        member.role = "OWNER"
        # Do NOT set is_super_admin here (that’s platform-level)
        db.commit()
        owner_created = False
    else:
        member = models.Member(
            email=owner_email,
            hashed_password=hashed,
            full_name="Club Owner",
            is_admin=True,
            is_active=True,
            club_id=club.id,
            role="OWNER",
            is_super_admin=False,
        )
        db.add(member)
        db.commit()
        db.refresh(member)
        owner_created = True

    # 6) Mark bootstrap used (permanent lock)
    db.execute(
        text(
            """
            INSERT INTO system_flags (key, value)
            VALUES ('bootstrap_used', '1')
            ON CONFLICT (key) DO UPDATE SET value='1'
            """
        )
    )
    db.commit()

    return {
        "ok": True,
        "club_slug": club.slug,
        "club_id": int(club.id),
        "owner_email": owner_email,
        "owner_id": int(member.id),
        "owner_created": bool(owner_created),
        "next_step": "REMOVE BOOTSTRAP_* env vars in Render, then redeploy.",
    }
