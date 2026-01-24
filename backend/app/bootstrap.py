# backend/app/bootstrap.py
from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter()


def _env(name: str) -> Optional[str]:
    v = os.getenv(name)
    return v.strip() if v else None


def _bootstrap_enabled() -> bool:
    """
    If BOOTSTRAP_KEY is missing, bootstrap is considered disabled.
    In production, we want the endpoint to behave like it does not exist.
    """
    return bool(_env("BOOTSTRAP_KEY"))


def _require_env(name: str) -> str:
    v = _env(name)
    if not v:
        # IMPORTANT: do NOT return 500 (looks like a server bug).
        # Treat missing bootstrap config as "route not found".
        raise HTTPException(status_code=404, detail="Not Found")
    return v


@router.post("/admin/bootstrap")
def bootstrap_first_owner(
    key: str = Query(..., description="Bootstrap key"),
    db: Session = Depends(get_db),
):
    """
    One-time bootstrap:
      - Creates a club (by code) if it doesn't exist
      - Creates an OWNER member if it doesn't exist
      - Writes a DB flag so it cannot be run again (even if env vars remain)

    Security:
      - If BOOTSTRAP_KEY is missing, respond 404 (acts like endpoint doesn't exist)
      - Requires BOOTSTRAP_KEY match
      - Permanently locks after first success via DB flag
      - You should remove BOOTSTRAP_* env vars after success
    """

    # If env is removed, do not expose anything.
    if not _bootstrap_enabled():
        raise HTTPException(status_code=404, detail="Not Found")

    bootstrap_key = _require_env("BOOTSTRAP_KEY")
    if not secrets.compare_digest(key, bootstrap_key):
        raise HTTPException(status_code=401, detail="Invalid bootstrap key")

    # Hard-disable after first run via DB flag
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS system_flags (
            key TEXT PRIMARY KEY,
            value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    used = db.execute(text("SELECT value FROM system_flags WHERE key='bootstrap_used'")).first()
    if used and used[0] == "1":
        raise HTTPException(status_code=403, detail="Bootstrap already used")

    club_code = _require_env("BOOTSTRAP_CLUB_CODE")
    club_name = _env("BOOTSTRAP_CLUB_NAME") or club_code
    owner_email = _require_env("BOOTSTRAP_EMAIL").lower()
    owner_password = _require_env("BOOTSTRAP_PASSWORD")

    # Password hashing: use passlib bcrypt (works with your deps)
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed = pwd_context.hash(owner_password)

    # 1) Ensure club exists
    club_row = db.execute(
        text("SELECT id FROM clubs WHERE code = :code"),
        {"code": club_code},
    ).first()

    if club_row:
        club_id = club_row[0]
    else:
        db.execute(
            text("""
                INSERT INTO clubs (code, name)
                VALUES (:code, :name)
            """),
            {"code": club_code, "name": club_name},
        )
        club_id = db.execute(
            text("SELECT id FROM clubs WHERE code = :code"),
            {"code": club_code},
        ).first()[0]

    # 2) Ensure owner member exists
    member_row = db.execute(
        text("SELECT id FROM members WHERE club_id = :club_id AND lower(email) = :email"),
        {"club_id": club_id, "email": owner_email},
    ).first()

    if member_row:
        db.execute(
            text("""
                UPDATE members
                SET hashed_password = :hp,
                    role = 'OWNER',
                    is_active = TRUE
                WHERE id = :id
            """),
            {"hp": hashed, "id": member_row[0]},
        )
        owner_id = member_row[0]
        created = False
    else:
        db.execute(
            text("""
                INSERT INTO members (club_id, email, hashed_password, role, is_active)
                VALUES (:club_id, :email, :hp, 'OWNER', TRUE)
            """),
            {"club_id": club_id, "email": owner_email, "hp": hashed},
        )
        owner_id = db.execute(
            text("SELECT id FROM members WHERE club_id = :club_id AND lower(email)=:email"),
            {"club_id": club_id, "email": owner_email},
        ).first()[0]
        created = True

    # 3) Mark bootstrap as used (permanent lock)
    db.execute(
        text("""
            INSERT INTO system_flags (key, value)
            VALUES ('bootstrap_used', '1')
            ON CONFLICT (key) DO UPDATE SET value='1'
        """)
    )

    db.commit()

    return {
        "ok": True,
        "club_code": club_code,
        "club_id": club_id,
        "owner_email": owner_email,
        "owner_id": owner_id,
        "owner_created": created,
        "next_step": "REMOVE BOOTSTRAP_* env vars in Render, then redeploy.",
    }
