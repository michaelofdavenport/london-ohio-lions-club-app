# backend/app/bootstrap.py
from __future__ import annotations

import os
import secrets
import traceback
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
    # If BOOTSTRAP_KEY is missing, behave like the endpoint does not exist.
    return bool(_env("BOOTSTRAP_KEY"))


def _require_env(name: str) -> str:
    v = _env(name)
    if not v:
        # Do NOT return 500 (looks like a bug). Pretend route doesn't exist.
        raise HTTPException(status_code=404, detail="Not Found")
    return v


def _ensure_table_and_columns(db: Session) -> None:
    """
    Make bootstrap resilient on a fresh DB:
      - system_flags table
      - clubs table with (id, slug, name)
      - members table with (id, club_id, email, hashed_password, role, is_active)
    If your real schema has *more* columns, this won't hurt it.
    If your schema uses different names, the error message will tell us exactly what to change.
    """

    # system_flags
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

    # clubs (minimal required for bootstrap)
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS clubs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL
            )
            """
        )
    )

    # members (minimal required for bootstrap)
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                club_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                hashed_password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'MEMBER',
                is_active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
    )

    db.commit()


@router.post("/admin/bootstrap")
def bootstrap_first_owner(
    key: str = Query(..., description="Bootstrap key"),
    db: Session = Depends(get_db),
):
    """
    One-time bootstrap:
      - Creates a club (by slug) if it doesn't exist
      - Creates an OWNER member if it doesn't exist (or upgrades existing)
      - Locks itself after first success via system_flags

    Security:
      - If BOOTSTRAP_KEY missing => 404 (acts like endpoint doesn't exist)
      - Requires BOOTSTRAP_KEY match
      - After first success => 403 forever
      - After success: remove BOOTSTRAP_* env vars in Render and redeploy
    """

    # If env is removed, do not expose anything.
    if not _bootstrap_enabled():
        raise HTTPException(status_code=404, detail="Not Found")

    bootstrap_key = _require_env("BOOTSTRAP_KEY")
    if not secrets.compare_digest(key, bootstrap_key):
        raise HTTPException(status_code=401, detail="Invalid bootstrap key")

    try:
        # Ensure required tables exist (fresh DB-safe)
        _ensure_table_and_columns(db)

        # Hard-disable after first run via DB flag
        used = db.execute(text("SELECT value FROM system_flags WHERE key='bootstrap_used'")).first()
        if used and str(used[0]) == "1":
            raise HTTPException(status_code=403, detail="Bootstrap already used")

        # IMPORTANT: use SLUG (matches your URLs: london-ohio)
        club_slug = _require_env("BOOTSTRAP_CLUB_SLUG")
        club_name = _env("BOOTSTRAP_CLUB_NAME") or club_slug

        owner_email = _require_env("BOOTSTRAP_EMAIL").strip().lower()
        owner_password = _require_env("BOOTSTRAP_PASSWORD")

        # Password hashing
        from passlib.context import CryptContext

        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        hashed = pwd_context.hash(owner_password)

        # 1) Ensure club exists (by slug)
        club_row = db.execute(
            text("SELECT id FROM clubs WHERE slug = :slug"),
            {"slug": club_slug},
        ).first()

        if club_row:
            club_id = int(club_row[0])
        else:
            db.execute(
                text("INSERT INTO clubs (slug, name) VALUES (:slug, :name)"),
                {"slug": club_slug, "name": club_name},
            )
            club_id = int(
                db.execute(
                    text("SELECT id FROM clubs WHERE slug = :slug"),
                    {"slug": club_slug},
                ).first()[0]
            )

        # 2) Ensure owner member exists (by club_id + email)
        member_row = db.execute(
            text(
                """
                SELECT id
                FROM members
                WHERE club_id = :club_id AND lower(email) = :email
                """
            ),
            {"club_id": club_id, "email": owner_email},
        ).first()

        if member_row:
            owner_id = int(member_row[0])
            db.execute(
                text(
                    """
                    UPDATE members
                    SET hashed_password = :hp,
                        role = 'OWNER',
                        is_active = 1
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
                    INSERT INTO members (club_id, email, hashed_password, role, is_active)
                    VALUES (:club_id, :email, :hp, 'OWNER', 1)
                    """
                ),
                {"club_id": club_id, "email": owner_email, "hp": hashed},
            )
            owner_id = int(
                db.execute(
                    text(
                        """
                        SELECT id
                        FROM members
                        WHERE club_id = :club_id AND lower(email) = :email
                        """
                    ),
                    {"club_id": club_id, "email": owner_email},
                ).first()[0]
            )
            created = True

        # 3) Mark bootstrap as used (permanent lock)
        db.execute(
            text(
                """
                INSERT INTO system_flags (key, value)
                VALUES ('bootstrap_used', '1')
                ON CONFLICT(key) DO UPDATE SET value='1'
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

    except HTTPException:
        # Let FastAPI return it cleanly
        raise

    except Exception as e:
        db.rollback()
        # Print full traceback to Render logs (so we can see the real failure)
        print("🔥 BOOTSTRAP FAILED")
        print(traceback.format_exc())
        # Return a useful error to the caller (temporarily)
        raise HTTPException(status_code=500, detail=f"Bootstrap error: {e}")
