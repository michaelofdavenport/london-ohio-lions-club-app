# app/routers/setup.py
from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/setup", tags=["setup"])


# -----------------------------
# Helpers
# -----------------------------
def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def _setup_force() -> bool:
    return _truthy(os.getenv("SETUP_FORCE"))


def _set_if_exists(obj: Any, field: str, value: Any) -> None:
    if hasattr(obj, field):
        setattr(obj, field, value)


def _render_error(msg: str) -> str:
    return f"""
    <html>
      <head><title>Setup Error</title></head>
      <body style="font-family: Arial, sans-serif; max-width: 700px; margin: 40px auto;">
        <h1 style="color:#b00020;">Setup Error</h1>
        <p>{msg}</p>
        <p><a href="/setup">Back to Setup</a></p>
      </body>
    </html>
    """


def _club_count(db: Session) -> int:
    return int(db.execute(select(func.count()).select_from(models.Club)).scalar_one())


def _member_count(db: Session) -> int:
    return int(db.execute(select(func.count()).select_from(models.Member)).scalar_one())


def _already_setup(db: Session) -> bool:
    """
    Setup is considered complete if there is at least one club AND at least one member.
    (This fixes your current situation: you have clubs, but zero members.)
    Unless SETUP_FORCE=true (always show setup page).
    """
    if _setup_force():
        return False
    return _club_count(db) > 0 and _member_count(db) > 0


def _get_first_club(db: Session) -> Optional[models.Club]:
    return db.execute(select(models.Club).order_by(models.Club.id.asc()).limit(1)).scalar_one_or_none()


def _hash_password(password: str):
    if hasattr(auth, "hash_password"):
        return auth.hash_password(password)
    if hasattr(auth, "get_password_hash"):
        return auth.get_password_hash(password)
    raise RuntimeError("No password hash function found on auth (hash_password/get_password_hash).")


# -----------------------------
# Routes
# -----------------------------
@router.get("", response_class=HTMLResponse)
def setup_page(db: Session = Depends(get_db)):
    if _already_setup(db):
        return RedirectResponse(url="/static/index.html", status_code=302)

    cc = _club_count(db)
    note = ""
    if cc > 0:
        note = f"<p style='color:#555; font-size: 12px;'>Note: I found {cc} club(s) already in the database. I will create the first owner for the first club.</p>"

    return f"""
    <html>
      <head><title>First-Time Setup</title></head>
      <body style="font-family: Arial, sans-serif; max-width: 700px; margin: 40px auto;">
        <h1>First-Time Setup</h1>
        <p>Create your first Owner account here.</p>
        {note}

        <form method="post" action="/setup" style="margin-top: 24px;">
          <h3>Club (optional)</h3>
          <p style="font-size:12px;color:#666;">If no clubs exist yet, we will create one. If clubs already exist, we will use the first one.</p>

          <label>Club Name</label><br/>
          <input name="club_name" style="width: 100%; padding: 8px;" placeholder="London Lions"/><br/><br/>

          <label>Club Slug (simple name, like: london-lions)</label><br/>
          <input name="club_slug" style="width: 100%; padding: 8px;" placeholder="london-lions"/><br/><br/>

          <h3>Owner Account</h3>
          <label>Owner Email</label><br/>
          <input name="email" type="email" required style="width: 100%; padding: 8px;"/><br/><br/>

          <label>Owner Password</label><br/>
          <input name="password" type="password" required style="width: 100%; padding: 8px;"/><br/><br/>

          <button type="submit" style="padding: 10px 14px;">Create Owner</button>
        </form>

        <hr style="margin: 24px 0;" />
        <p style="font-size: 12px; color: #666;">
          Tip: For testing, set <b>SETUP_FORCE=true</b> in .env, restart server, then visit <b>/setup</b>.
        </p>
      </body>
    </html>
    """


@router.post("", response_class=HTMLResponse)
async def run_setup(request: Request, db: Session = Depends(get_db)):
    if _already_setup(db):
        return _render_error("Setup already completed.")

    form = await request.form()
    club_name = (form.get("club_name") or "").strip()
    club_slug = (form.get("club_slug") or "").strip()
    email = (form.get("email") or "").strip().lower()
    password = (form.get("password") or "").strip()

    if not (email and password):
        return _render_error("Missing required fields: owner email and password are required.")

    # Prevent duplicate email
    existing_member = db.execute(select(models.Member).where(models.Member.email == email)).scalar_one_or_none()
    if existing_member:
        return _render_error("That owner email already exists. Pick a different email.")

    # 1) Find or create club
    try:
        club = _get_first_club(db)

        if club is None:
            # No clubs exist -> create one (require name/slug)
            if not (club_name and club_slug):
                return _render_error("No clubs exist yet. Please enter Club Name and Club Slug.")

            # slug uniqueness
            if hasattr(models.Club, "slug"):
                existing = db.execute(select(models.Club).where(models.Club.slug == club_slug)).scalar_one_or_none()
                if existing:
                    return _render_error("Club slug already exists. Choose a different slug.")

            club = models.Club()
            _set_if_exists(club, "name", club_name)
            _set_if_exists(club, "slug", club_slug)
            _set_if_exists(club, "plan", "FREE")
            _set_if_exists(club, "subscription_status", "inactive")

            db.add(club)
            db.commit()
            db.refresh(club)

    except Exception as e:
        db.rollback()
        return _render_error(f"Could not find/create club. Error: {type(e).__name__}")

    # 2) Create owner member
    try:
        hashed = _hash_password(password)

        owner = models.Member()
        _set_if_exists(owner, "email", email)
        _set_if_exists(owner, "hashed_password", hashed)
        _set_if_exists(owner, "club_id", getattr(club, "id", None))

        # common flags
        _set_if_exists(owner, "is_owner", True)
        _set_if_exists(owner, "is_admin", True)

        # role strings if used
        if hasattr(owner, "role") and not getattr(owner, "role", None):
            setattr(owner, "role", "OWNER")
        if hasattr(owner, "roles") and not getattr(owner, "roles", None):
            setattr(owner, "roles", "OWNER")

        db.add(owner)
        db.commit()

    except Exception as e:
        db.rollback()
        return _render_error(f"Could not create owner. Error: {type(e).__name__}")

    return RedirectResponse(url="/static/index.html?setup=done", status_code=302)


@router.get("/debug")
def setup_debug(db: Session = Depends(get_db)):
    return {
        "ok": True,
        "setup_force": _setup_force(),
        "club_count": _club_count(db),
        "member_count": _member_count(db),
    }
