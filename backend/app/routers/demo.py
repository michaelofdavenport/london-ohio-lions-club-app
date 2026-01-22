# app/routers/demo.py
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/admin/demo", tags=["demo"])


# -----------------------------
# Helpers
# -----------------------------
def _set_if_exists(obj: Any, field: str, value: Any) -> None:
    if hasattr(obj, field):
        setattr(obj, field, value)


def _demo_email(i: int) -> str:
    return f"demo+member{i}@example.com"


def _ensure_owner(member: models.Member) -> None:
    # You already have require_owner in auth; use it if available.
    # If your auth module has auth.require_owner, use that instead by swapping dependency below.
    if not getattr(member, "is_owner", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required.")


def _find_request_model():
    """
    Try to find your 'service request' model safely.
    We will support common names. If none found, demo requests will be skipped.
    """
    for name in ("ServiceRequest", "Request", "PublicRequest", "ServiceOrder", "Ticket"):
        if hasattr(models, name):
            return getattr(models, name)
    return None


def _is_demo_member(m: models.Member) -> bool:
    email = (getattr(m, "email", "") or "").lower()
    return email.startswith("demo+member") and email.endswith("@example.com")


def _is_demo_request(r: Any) -> bool:
    # If model has is_demo flag, use it
    if hasattr(r, "is_demo"):
        return bool(getattr(r, "is_demo"))
    # Otherwise, look for a title/summary marker
    for field in ("title", "subject", "summary", "description"):
        if hasattr(r, field):
            v = (getattr(r, field) or "")
            if isinstance(v, str) and v.startswith("[DEMO]"):
                return True
    return False


# -----------------------------
# Routes
# -----------------------------
@router.get("/status")
def demo_status(
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    _ensure_owner(member)

    # Demo members
    demo_member_count = db.execute(select(func.count()).select_from(models.Member)).scalar_one()
    # count only demo members
    demo_member_count = db.execute(
        select(func.count()).select_from(models.Member).where(models.Member.email.like("demo+member%@example.com"))
    ).scalar_one()

    # Demo requests (optional)
    ReqModel = _find_request_model()
    demo_request_count = 0
    if ReqModel is not None:
        # If ReqModel has is_demo, count that, else do a best-effort marker check
        if hasattr(ReqModel, "is_demo"):
            demo_request_count = db.execute(select(func.count()).select_from(ReqModel).where(ReqModel.is_demo == True)).scalar_one()  # type: ignore
        else:
            # Try field like title/subject
            field = None
            for f in ("title", "subject", "summary", "description"):
                if hasattr(ReqModel, f):
                    field = getattr(ReqModel, f)
                    break
            if field is not None:
                demo_request_count = db.execute(
                    select(func.count()).select_from(ReqModel).where(field.like("[DEMO]%"))
                ).scalar_one()

    return {
        "ok": True,
        "demo_members": int(demo_member_count),
        "demo_requests": int(demo_request_count),
        "request_model_detected": ReqModel.__name__ if ReqModel is not None else None,
    }


@router.post("/load")
def demo_load(
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    """
    Creates demo members + demo service requests for the member's club.
    Safe: if no request model found, it will still load members.
    """
    _ensure_owner(member)

    club_id = member.club_id

    # 1) Create demo members (if they don't already exist)
    created_members = 0
    for i in range(1, 6):  # 5 demo members
        email = _demo_email(i)
        existing = db.execute(select(models.Member).where(models.Member.email == email)).scalar_one_or_none()
        if existing:
            continue

        m = models.Member(
            email=email,
            hashed_password=auth.hash_password("DemoPassword123!"),
            club_id=club_id,
        )
        _set_if_exists(m, "is_demo", True)
        _set_if_exists(m, "is_owner", False)

        # Optional nice fields if your model has them
        _set_if_exists(m, "name", f"Demo Member {i}")
        _set_if_exists(m, "full_name", f"Demo Member {i}")

        db.add(m)
        created_members += 1

    db.commit()

    # 2) Create demo service requests (best-effort)
    ReqModel = _find_request_model()
    created_requests = 0

    if ReqModel is not None:
        # Make 8 demo requests
        demo_titles = [
            "[DEMO] Eyeglasses assistance request",
            "[DEMO] Community help needed - ride to appointment",
            "[DEMO] Volunteer signup inquiry",
            "[DEMO] Food pantry donation pickup",
            "[DEMO] Vision screening event question",
            "[DEMO] General help request",
            "[DEMO] Follow-up needed on prior request",
            "[DEMO] Thank-you note / closure",
        ]

        for idx, title in enumerate(demo_titles, start=1):
            r = ReqModel()  # type: ignore

            # Common required-ish fields:
            _set_if_exists(r, "club_id", club_id)
            _set_if_exists(r, "member_id", member.id)

            # Mark demo
            _set_if_exists(r, "is_demo", True)

            # Try to set a title/subject/summary field
            if hasattr(r, "title"):
                setattr(r, "title", title)
            elif hasattr(r, "subject"):
                setattr(r, "subject", title)
            elif hasattr(r, "summary"):
                setattr(r, "summary", title)
            elif hasattr(r, "description"):
                setattr(r, "description", title)
            else:
                # If your request model has none of these, we can't safely fill it.
                continue

            # Optional status field if exists
            _set_if_exists(r, "status", "NEW")

            # Optional contact fields if exist
            _set_if_exists(r, "requester_name", f"Demo Requester {idx}")
            _set_if_exists(r, "requester_email", f"demo.requester{idx}@example.com")
            _set_if_exists(r, "phone", "555-0100")

            db.add(r)
            created_requests += 1

        db.commit()

    return {
        "ok": True,
        "created_demo_members": created_members,
        "created_demo_requests": created_requests,
        "request_model_detected": ReqModel.__name__ if ReqModel is not None else None,
    }


@router.post("/clear")
def demo_clear(
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    """
    Deletes demo members + demo service requests.
    Safe: only deletes rows we can confidently identify as demo.
    """
    _ensure_owner(member)

    # 1) Delete demo requests (optional)
    ReqModel = _find_request_model()
    deleted_requests = 0
    if ReqModel is not None:
        rows = db.execute(select(ReqModel)).scalars().all()  # type: ignore
        for r in rows:
            if _is_demo_request(r):
                db.delete(r)
                deleted_requests += 1
        db.commit()

    # 2) Delete demo members
    rows = db.execute(select(models.Member)).scalars().all()
    deleted_members = 0
    for m in rows:
        if _is_demo_member(m):
            db.delete(m)
            deleted_members += 1
    db.commit()

    return {
        "ok": True,
        "deleted_demo_members": deleted_members,
        "deleted_demo_requests": deleted_requests,
        "request_model_detected": ReqModel.__name__ if ReqModel is not None else None,
    }
