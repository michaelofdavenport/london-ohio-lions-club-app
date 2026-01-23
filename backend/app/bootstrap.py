# backend/app/bootstrap.py
from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app import auth

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
    One-time bootstrap for a brand-new Postgres DB:
      - Creates a club (by slug) if it doesn't exist
      - Creates/updates an OWNER member for that club
      - Writes a DB flag so it cannot be run again
    Security:
      - Requires BOOTSTRAP_KEY match
      - You should REMOVE BOOTSTRAP_* env vars after success
    """

    # 0) Check bootstrap key
    bootstrap_key = _require_env("BOOTSTRAP_KEY")
    if not secrets.compare_digest(key, bootstrap_key):
        raise HTTPException(status_code=401, detail="Invalid bootstrap key")

    # 1) Hard-disable after first run via DB flag
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS system_flags (
                key TEXT PRIMARY KEY,
                value TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
    )
    used = db.execute(text("SELECT value FROM system_flags WHERE key='bootstrap_used'")).first()
    if used and used[0] == "1":
        raise HTTPException(status_code=403, detail="Bootstrap already used")

    # 2) Read required env vars
    club_slug = _require_env("BOOTSTRAP_CLUB_CODE").strip().lower()  # we store this into clubs.slug
    club_name = _env("BOOTSTRAP_CLUB_NAME") or club_slug
    owner_email = _require_env("BOOTSTRAP_EMAIL").strip().lower()
    owner_password = _require_env("BOOTSTRAP_PASSWORD")

    # 3) Ensure club exists (your app uses clubs.slug, not clubs.code)
    club_row = db.execute(
        text("SELECT id FROM clubs WHERE slug = :slug"),
        {"slug": club_slug},
    ).first()

    if club_row:
        club_id = int(club_row[0])
        # Keep name fresh if provided
        db.execute(
            text("UPDATE clubs SET name = :name WHERE id = :id"),
            {"name": club_name, "id": club_id},
        )
    else:
        # Insert with the columns your app already uses in main.py
        db.execute(
            text(
                """
                INSERT INTO clubs (slug, name, logo_url, is_active)
                VALUES (:slug, :name, :logo_url, TRUE)
                """
            ),
            {
                "slug": club_slug,
                "name": club_name,
                "logo_url": "/static/images/lions_emblem.png",
            },
        )
        club_id = int(
            db.execute(
                text("SELECT id FROM clubs WHERE slug = :slug"),
                {"slug": club_slug},
            ).first()[0]
        )

    # 4) Ensure OWNER member exists for that club
    member_row = db.execute(
        text("SELECT id FROM members WHERE club_id = :club_id AND lower(email) = :email"),
        {"club_id": club_id, "email": owner_email},
    ).first()

    hashed = auth.hash_password(owner_password)

    if member_row:
        owner_id = int(member_row[0])
        db.execute(
            text(
                """
                UPDATE members
                SET hashed_password = :hp,
                    role = 'OWNER',
                    is_active = TRUE,
                    is_admin = TRUE,
                    is_super_admin = TRUE
                WHERE id = :id
                """
            ),
            {"hp": hashed, "id": owner_id},
        )
        created = False
    else:
        db.execute(
            text(
                """
                INSERT INTO members (club_id, email, hashed_password, role, is_active, is_admin, is_super_admin, full_name)
                VALUES (:club_id, :email, :hp, 'OWNER', TRUE, TRUE, TRUE, :full_name)
                """
            ),
            {
                "club_id": club_id,
                "email": owner_email,
                "hp": hashed,
                "full_name": "Owner",
            },
        )
        owner_id = int(
            db.execute(
                text("SELECT id FROM members WHERE club_id = :club_id AND lower(email)=:email"),
                {"club_id": club_id, "email": owner_email},
            ).first()[0]
        )
        created = True

    # 5) Mark bootstrap as used (permanent lock)
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
        "club_slug": club_slug,
        "club_id": club_id,
        "owner_email": owner_email,
        "owner_id": owner_id,
        "owner_created": created,
        "next_step": "REMOVE BOOTSTRAP_* env vars in Render, then redeploy.",
    }
