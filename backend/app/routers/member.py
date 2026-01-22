# app/routers/member.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.database import get_db
from app.emailer import send_email_if_configured
from app.email_templates import requester_decision

# ✅ Phase 4 Option B: Free trial then hard lock
from app.trial_guard import require_active_access


router = APIRouter(
    prefix="/member",
    tags=["member"],
    dependencies=[
        Depends(auth.get_current_member),  # ✅ router-wide login requirement ONLY
        # ❌ DO NOT enforce require_active_access router-wide
    ],
)

# -------------------------------------------------
# BOOTSTRAP ENDPOINTS (AUTH-ONLY, NEVER LOCKED)
# -------------------------------------------------

@router.get("/me", response_model=schemas.MemberOut)
def member_me(member: models.Member = Depends(auth.get_current_member)):
    return member


@router.get("/service-hours/summary")
def member_service_hours_summary(
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    year = datetime.utcnow().year

    club_ytd_hours = db.scalar(
        select(func.coalesce(func.sum(models.ServiceHour.hours), 0.0))
        .where(func.strftime("%Y", models.ServiceHour.service_date) == str(year))
        .where(models.ServiceHour.club_id == member.club_id)
    ) or 0.0

    return {"year": year, "club_ytd_hours": float(club_ytd_hours)}


@router.get("/requests/summary")
def member_requests_summary(
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    rows_status = db.execute(
        select(models.Request.status, func.count(models.Request.id))
        .where(models.Request.club_id == member.club_id)
        .group_by(models.Request.status)
    ).all()

    rows_category = db.execute(
        select(models.Request.category, func.count(models.Request.id))
        .where(models.Request.club_id == member.club_id)
        .group_by(models.Request.category)
    ).all()

    return {
        "total": db.scalar(select(func.count(models.Request.id)).where(models.Request.club_id == member.club_id)) or 0,
        "by_status": dict(rows_status),
        "by_category": dict(rows_category),
    }


# -------------------------------------------------
# MEMBER PROFILE (locked because it’s “app usage”)
# -------------------------------------------------

@router.put("/me", response_model=schemas.MemberOut, dependencies=[Depends(require_active_access)])
def member_update_me(
    payload: schemas.MemberUpdateMe,
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    member.full_name = payload.full_name
    member.phone = payload.phone
    member.address = payload.address
    member.member_since = payload.member_since
    member.birthday = payload.birthday

    db.commit()
    db.refresh(member)
    return member


# -------------------------------------------------
# APP USAGE ENDPOINTS (LOCKED)
# -------------------------------------------------

@router.get("/roster", response_model=list[schemas.MemberOut], dependencies=[Depends(require_active_access)])
def member_roster(
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    stmt = (
        select(models.Member)
        .where(models.Member.is_active == True)  # noqa: E712
        .where(models.Member.club_id == member.club_id)
        .order_by(func.coalesce(models.Member.full_name, "ZZZ"), models.Member.email)
    )
    return db.scalars(stmt).all()


@router.get("/requests", response_model=list[schemas.RequestOut], dependencies=[Depends(require_active_access)])
def member_list_requests(
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    stmt = select(models.Request).where(models.Request.club_id == member.club_id)
    if status_filter:
        stmt = stmt.where(models.Request.status == status_filter)
    return db.scalars(stmt.order_by(models.Request.created_at.desc())).all()


@router.patch(
    "/requests/{request_id}/review",
    response_model=schemas.RequestOut,
    dependencies=[Depends(require_active_access)],
)
def member_review_request(
    request_id: int,
    payload: schemas.RequestReviewIn,
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    req = db.get(models.Request, request_id)
    if not req or req.club_id != member.club_id:
        raise HTTPException(status_code=404, detail="Request not found")

    if req.status != "PENDING":
        raise HTTPException(status_code=400, detail="Request already reviewed")

    req.status = payload.status
    req.decision_note = payload.decision_note
    req.reviewed_by_member_id = member.id
    req.reviewed_at = datetime.utcnow()
    req.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(req)

    # Email: requester decision (optional)
    if req.requester_email and req.status in ("APPROVED", "DENIED"):
        parts = requester_decision(
            org_name="London Lions",
            request_id=req.id,
            category=req.category,
            decision=req.status,
            requester_name=req.requester_name,
            decision_note=req.decision_note,
            base_url=(schemas.APP_BASE_URL if hasattr(schemas, "APP_BASE_URL") else ""),
        )
        ok = send_email_if_configured(req.requester_email, parts.subject, parts.body)
        if not ok:
            print("EMAIL NOT SENT (disabled/missing config/SMTP failed).")

    return req


# =================================================
# ✅ EVENTS (CONTRACT-FIRST)
# Endpoints your events.js calls:
#   GET    /member/events?include_past=true
#   POST   /member/events
#   PUT    /member/events/{event_id}
#   DELETE /member/events/{event_id}
#
# IMPORTANT:
# - LIST is NOT paywalled (so you can still see events when locked)
# - CREATE/UPDATE/DELETE are paywalled + admin-only
# =================================================

class EventUpsertIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    location: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    start_at: str = Field(..., description="UTC-naive ISO string: YYYY-MM-DDTHH:MM:SS")
    end_at: Optional[str] = Field(None, description="UTC-naive ISO string: YYYY-MM-DDTHH:MM:SS")
    is_public: bool = True


def _parse_iso_naive_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # accepts "2026-01-15T11:10:00"
        return datetime.fromisoformat(str(s).strip())
    except Exception:
        return None


@router.get("/events", response_model=list[schemas.EventOut])
def member_list_events(
    include_past: bool = Query(False),
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    now = datetime.utcnow()
    stmt = select(models.Event).where(models.Event.club_id == member.club_id)

    if not include_past:
        stmt = stmt.where(models.Event.start_at >= now)

    return db.scalars(stmt.order_by(models.Event.start_at.asc())).all()


@router.post(
    "/events",
    response_model=schemas.EventOut,
    status_code=201,
    dependencies=[Depends(require_active_access)],
)
def member_create_event(
    payload: EventUpsertIn,
    db: Session = Depends(get_db),
    admin: models.Member = Depends(auth.require_admin),  # ✅ admin-only
):
    start_dt = _parse_iso_naive_dt(payload.start_at)
    end_dt = _parse_iso_naive_dt(payload.end_at)

    if not start_dt:
        raise HTTPException(status_code=400, detail="Invalid start_at (expected ISO like 2026-01-14T18:30:00)")
    if end_dt and end_dt <= start_dt:
        raise HTTPException(status_code=400, detail="end_at must be after start_at")

    ev = models.Event(
        club_id=admin.club_id,
        title=payload.title.strip(),
        location=payload.location.strip(),
        description=(payload.description or "").strip() or None,
        start_at=start_dt,
        end_at=end_dt,
        is_public=bool(payload.is_public),
        created_at=datetime.utcnow() if hasattr(models.Event, "created_at") else None,
    )

    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


@router.put(
    "/events/{event_id}",
    response_model=schemas.EventOut,
    dependencies=[Depends(require_active_access)],
)
def member_update_event(
    event_id: int,
    payload: EventUpsertIn,
    db: Session = Depends(get_db),
    admin: models.Member = Depends(auth.require_admin),  # ✅ admin-only
):
    ev = db.get(models.Event, event_id)
    if not ev or ev.club_id != admin.club_id:
        raise HTTPException(status_code=404, detail="Event not found")

    start_dt = _parse_iso_naive_dt(payload.start_at)
    end_dt = _parse_iso_naive_dt(payload.end_at)

    if not start_dt:
        raise HTTPException(status_code=400, detail="Invalid start_at (expected ISO like 2026-01-14T18:30:00)")
    if end_dt and end_dt <= start_dt:
        raise HTTPException(status_code=400, detail="end_at must be after start_at")

    ev.title = payload.title.strip()
    ev.location = payload.location.strip()
    ev.description = (payload.description or "").strip() or None
    ev.start_at = start_dt
    ev.end_at = end_dt
    ev.is_public = bool(payload.is_public)

    db.commit()
    db.refresh(ev)
    return ev


@router.delete(
    "/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_active_access)],
)
def member_delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    admin: models.Member = Depends(auth.require_admin),  # ✅ admin-only
):
    ev = db.get(models.Event, event_id)
    if not ev or ev.club_id != admin.club_id:
        raise HTTPException(status_code=404, detail="Event not found")

    db.delete(ev)
    db.commit()
    return


# -------------------------------------------------
# SERVICE HOURS (LOCKED)
# -------------------------------------------------

@router.post(
    "/service-hours",
    response_model=schemas.ServiceHourOut,
    status_code=201,
    dependencies=[Depends(require_active_access)],
)
def member_log_service_hours(
    payload: schemas.ServiceHourCreateIn,
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    entry = models.ServiceHour(member_id=member.id, club_id=member.club_id, **payload.dict())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/service-hours", response_model=list[schemas.ServiceHourOut], dependencies=[Depends(require_active_access)])
def member_list_service_hours(
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    stmt = (
        select(models.ServiceHour)
        .where(models.ServiceHour.member_id == member.id)
        .where(models.ServiceHour.club_id == member.club_id)
        .order_by(models.ServiceHour.service_date.desc())
    )
    return db.scalars(stmt).all()


@router.patch(
    "/service-hours/{entry_id}",
    response_model=schemas.ServiceHourOut,
    dependencies=[Depends(require_active_access)],
)
def member_update_service_hours(
    entry_id: int,
    payload: schemas.ServiceHourUpdateIn,
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    entry = db.get(models.ServiceHour, entry_id)
    if not entry or entry.club_id != member.club_id:
        raise HTTPException(status_code=404, detail="Service hour entry not found")

    if entry.member_id != member.id:
        raise HTTPException(status_code=403, detail="Not allowed to edit this entry")

    if payload.service_date is not None:
        entry.service_date = payload.service_date
    if payload.hours is not None:
        entry.hours = payload.hours
    if payload.activity is not None:
        entry.activity = payload.activity
    if payload.notes is not None:
        entry.notes = payload.notes

    db.commit()
    db.refresh(entry)
    return entry


@router.delete(
    "/service-hours/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_active_access)],
)
def member_delete_service_hours(
    entry_id: int,
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    entry = db.get(models.ServiceHour, entry_id)
    if not entry or entry.club_id != member.club_id:
        raise HTTPException(status_code=404, detail="Service hour entry not found")

    if entry.member_id != member.id:
        raise HTTPException(status_code=403, detail="Not allowed to delete this entry")

    db.delete(entry)
    db.commit()
    return
