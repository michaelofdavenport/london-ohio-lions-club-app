# app/main.py
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import os

from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app import models, schemas, auth
from app.emailer import send_email_if_configured

from app.routers import dashboard
from app.routers import admin_requests
from app.routers import admin_email
from app.routers import admin_events  # ✅ Invite members to event


# -------------------------------------------------
# LOAD .env ONCE (top of file, before any getenv use)
# -------------------------------------------------
_env_path = find_dotenv(usecwd=True)
load_dotenv(_env_path, override=True)

# Optional boot debug (safe): only prints if DEBUG_ENV=1
if (os.getenv("DEBUG_ENV") or "").strip().lower() in ("1", "true", "yes", "on"):
    print("DOTENV PATH =", _env_path)
    print("SMTP_HOST =", os.getenv("SMTP_HOST"))
    print("SMTP_USERNAME =", os.getenv("SMTP_USERNAME"))


# -------------------------------------------------
# EMAIL TIME HELPERS (US/Eastern for ALL emails)
# NO ZoneInfo / NO tzdata (Windows-safe)
# -------------------------------------------------
# Backend stores datetimes as naive UTC strings "YYYY-MM-DDTHH:MM:SS"
# We treat them as UTC, then convert to Eastern with DST rules.
# DST rules (US):
# - Starts: 2nd Sunday in March at 2:00 AM local (EST -> EDT)
# - Ends:   1st Sunday in November at 2:00 AM local (EDT -> EST)
# -------------------------------------------------

def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> datetime:
    """
    Return the date of the n-th occurrence of weekday in a month.
    weekday: Monday=0 ... Sunday=6
    """
    first = datetime(year, month, 1)
    delta_days = (weekday - first.weekday()) % 7
    day = 1 + delta_days + (n - 1) * 7
    return datetime(year, month, day)


def _first_weekday_of_month(year: int, month: int, weekday: int) -> datetime:
    return _nth_weekday_of_month(year, month, weekday, 1)


def _us_eastern_dst_range_utc(year: int) -> tuple[datetime, datetime]:
    """
    Returns DST start/end instants in UTC for US Eastern time for given year.

    DST start: 2nd Sunday in March at 2:00 AM local time.
      At that instant, local time is transitioning from EST (UTC-5) to EDT (UTC-4).
      2:00 AM EST == 07:00 UTC.

    DST end: 1st Sunday in November at 2:00 AM local time.
      At that instant, local time is transitioning from EDT (UTC-4) to EST (UTC-5).
      2:00 AM EDT == 06:00 UTC.
    """
    # 2nd Sunday in March
    dst_start_local = _nth_weekday_of_month(year, 3, weekday=6, n=2).replace(
        hour=2, minute=0, second=0, microsecond=0
    )
    dst_start_utc = dst_start_local + timedelta(hours=5)  # convert from EST to UTC

    # 1st Sunday in November
    dst_end_local = _first_weekday_of_month(year, 11, weekday=6).replace(
        hour=2, minute=0, second=0, microsecond=0
    )
    dst_end_utc = dst_end_local + timedelta(hours=4)  # convert from EDT to UTC

    return dst_start_utc, dst_end_utc


def _is_us_eastern_dst(utc_dt: datetime) -> bool:
    """
    Determine if a UTC datetime is within US Eastern DST.
    utc_dt must be treated as UTC (naive is okay as long as it's UTC).
    """
    dst_start_utc, dst_end_utc = _us_eastern_dst_range_utc(utc_dt.year)
    return dst_start_utc <= utc_dt < dst_end_utc


def _utc_naive_to_eastern(utc_naive: datetime) -> datetime:
    """
    Convert a UTC-naive datetime (assumed UTC) to Eastern local time (naive).
    """
    if _is_us_eastern_dst(utc_naive):
        return utc_naive - timedelta(hours=4)  # EDT
    return utc_naive - timedelta(hours=5)      # EST


def _parse_utc_naive(utc_naive: Optional[str]) -> Optional[datetime]:
    """
    Parse "YYYY-MM-DDTHH:MM:SS" (UTC-naive) to a naive datetime assumed UTC.
    """
    if not utc_naive:
        return None
    try:
        return datetime.fromisoformat(str(utc_naive).strip())
    except Exception:
        return None


def _fmt_eastern_from_utc_naive_dt(dt_utc_naive: Optional[datetime]) -> str:
    """
    Format exactly: MM/DD/YYYY at h:mm AM/PM (ET)
    """
    if not dt_utc_naive:
        return "—"

    et = _utc_naive_to_eastern(dt_utc_naive.replace(tzinfo=None))

    mm = et.strftime("%m")
    dd = et.strftime("%d")
    yyyy = et.strftime("%Y")
    hour = et.strftime("%I").lstrip("0") or "12"
    minute = et.strftime("%M")
    ampm = et.strftime("%p")

    return f"{mm}/{dd}/{yyyy} at {hour}:{minute} {ampm} (ET)"


def format_eastern_range(start_utc_naive: Optional[str], end_utc_naive: Optional[str]) -> str:
    """
    Input strings are UTC-naive. Output is the range in ET format.
    """
    s = _parse_utc_naive(start_utc_naive)
    e = _parse_utc_naive(end_utc_naive)
    if not s:
        return "—"
    if not e:
        return _fmt_eastern_from_utc_naive_dt(s)
    return f"{_fmt_eastern_from_utc_naive_dt(s)} \u2192 {_fmt_eastern_from_utc_naive_dt(e)}"


# -------------------------------------------------
# DB SETUP
# -------------------------------------------------
Base.metadata.create_all(bind=engine)


# -------------------------------------------------
# APP SETUP
# -------------------------------------------------
app = FastAPI(title="London Lions Backend", version="0.3.0")

# Static assets (JS/CSS/images)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# ✅ Block ONLY the admin tools HTML from being directly accessed
@app.get("/static/admin_tools.html")
def block_admin_tools_direct():
    raise HTTPException(status_code=404, detail="Not found")


# Routers
app.include_router(dashboard.router)
app.include_router(admin_requests.router)
app.include_router(admin_email.router)
app.include_router(admin_events.router)


# ✅ Admin-only HTML endpoint
@app.get("/admin/tools")
def admin_tools_page(admin: models.Member = Depends(auth.require_admin)):
    html_path = Path("app/static/admin_tools.html")
    return FileResponse(str(html_path))


# -------------------------------------------------
# ROOT + HEALTH
# -------------------------------------------------
@app.get("/")
def root():
    return RedirectResponse(url="/static/public_request.html")


@app.get("/health")
def health():
    return {"status": "ok"}


# -------------------------------------------------
# STARTUP: SQLITE SAFE MIGRATIONS + OPTIONAL DEFAULT ADMIN SEED
# -------------------------------------------------
def _sqlite_add_column_if_missing(db: Session, table_name: str, col_name: str, col_type_sql: str) -> None:
    try:
        rows = db.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        existing = {r[1] for r in rows}
        if col_name not in existing:
            db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type_sql}"))
            db.commit()
    except Exception:
        db.rollback()


@app.on_event("startup")
def bootstrap_startup():
    db = next(get_db())
    try:
        # members
        _sqlite_add_column_if_missing(db, "members", "member_since", "DATE")
        _sqlite_add_column_if_missing(db, "members", "birthday", "DATE")

        # requests workflow columns (safe add)
        _sqlite_add_column_if_missing(db, "requests", "assigned_to_member_id", "INTEGER")
        _sqlite_add_column_if_missing(db, "requests", "assigned_at", "DATETIME")
        _sqlite_add_column_if_missing(db, "requests", "closed_at", "DATETIME")
        _sqlite_add_column_if_missing(db, "requests", "priority", "TEXT")
        _sqlite_add_column_if_missing(db, "requests", "updated_at", "DATETIME")

        # ✅ MARKET-READY: seed admin ONLY when explicitly enabled
        seed_admin = (os.getenv("SEED_ADMIN") or "").strip().lower() in ("1", "true", "yes", "on")
        if seed_admin:
            admin_exists = db.scalar(select(models.Member).where(models.Member.is_admin == True))  # noqa: E712
            if not admin_exists:
                admin_email = (os.getenv("SEED_ADMIN_EMAIL") or "admin@example.com").strip()
                admin_password = (os.getenv("SEED_ADMIN_PASSWORD") or "AdminPassword123!").strip()

                admin_user = models.Member(
                    email=admin_email,
                    hashed_password=auth.hash_password(admin_password),
                    full_name="Default Admin",
                    is_admin=True,
                    is_active=True,
                )
                db.add(admin_user)
                db.commit()
    finally:
        db.close()


# -------------------------------------------------
# AUTH / LOGIN
# -------------------------------------------------
@app.post("/member/login", response_model=schemas.TokenOut)
def member_login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    email = form_data.username
    password = form_data.password

    member = db.scalar(select(models.Member).where(models.Member.email == email))
    if not member or not auth.verify_password(password, member.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not member.is_active:
        raise HTTPException(status_code=403, detail="Member is inactive")

    token = auth.create_access_token(subject=member.email)
    return schemas.TokenOut(access_token=token)


# -------------------------------------------------
# ROLE / PERMISSION PROOF
# -------------------------------------------------
@app.get("/admin/ping")
def admin_ping(admin: models.Member = Depends(auth.require_admin)):
    return {"ok": True, "admin_email": admin.email}


# -------------------------------------------------
# PUBLIC ENDPOINTS
# -------------------------------------------------
@app.post("/public/requests", response_model=schemas.RequestOut, status_code=201)
def public_create_request(payload: schemas.PublicRequestCreate, db: Session = Depends(get_db)):
    req = models.Request(
        category=payload.category,
        requester_name=payload.requester_name,
        requester_phone=payload.requester_phone,
        requester_email=str(payload.requester_email) if payload.requester_email else None,
        requester_address=payload.requester_address,
        description=payload.description,
        status="PENDING",
        updated_at=datetime.utcnow(),
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    # 1) EMAIL RECEIPT TO REQUESTER (if provided email)
    if req.requester_email:
        subject = f"London Lions – Request Received (#{req.id})"
        body = (
            f"Hello {req.requester_name},\n\n"
            f"We received your request and it is now being reviewed by the London, Ohio Lions Club.\n\n"
            f"Request ID: {req.id}\n"
            f"Category: {req.category}\n"
            f"Current Status: {req.status}\n\n"
            f"Thank you,\n"
            f"London Lions Club\n"
        )
        ok = send_email_if_configured(req.requester_email, subject, body)
        if not ok:
            print("EMAIL RECEIPT NOT SENT (disabled/missing config/SMTP failed).")

    # 2) OPTIONAL EMAIL TO ADMIN (if configured)
    admin_to = (os.getenv("ADMIN_NOTIFY_EMAIL") or os.getenv("SMTP_FROM_EMAIL") or "").strip()
    if admin_to:
        subject = f"New Request #{req.id} ({req.category})"
        body = (
            f"A new request was submitted.\n\n"
            f"ID: {req.id}\n"
            f"Category: {req.category}\n"
            f"Name: {req.requester_name}\n"
            f"Email: {req.requester_email or '—'}\n"
            f"Phone: {req.requester_phone or '—'}\n"
            f"Address: {req.requester_address or '—'}\n\n"
            f"Description:\n{req.description}\n"
        )
        ok = send_email_if_configured(admin_to, subject, body)
        if not ok:
            print("EMAIL ADMIN NOTIFY NOT SENT (disabled/missing config/SMTP failed).")

    return req


@app.get("/public/events", response_model=list[schemas.EventOut])
def public_list_events(include_past: bool = False, db: Session = Depends(get_db)):
    now = datetime.utcnow()
    stmt = select(models.Event).where(models.Event.is_public == True)  # noqa: E712
    if not include_past:
        stmt = stmt.where(models.Event.start_at >= now)
    return db.scalars(stmt.order_by(models.Event.start_at.asc())).all()


# -------------------------------------------------
# ADMIN: EMAIL TEST (Gmail SMTP)
# -------------------------------------------------
@app.post("/admin/email/test")
def admin_send_test_email(
    to_email: Optional[str] = Query(None),
    admin: models.Member = Depends(auth.require_admin),
):
    target = (to_email or admin.email or "").strip()
    if not target:
        raise HTTPException(status_code=400, detail="Missing to_email and admin has no email")

    subject = "London Lions – Test Email"
    body = (
        "This is a test email from London Lions Admin Tools.\n\n"
        "If you received this, SMTP is configured correctly.\n"
    )

    ok = send_email_if_configured(target, subject, body)
    return {"ok": bool(ok), "to": target}


# -------------------------------------------------
# ADMIN (used by admin_tools.js)
# -------------------------------------------------
@app.get("/admin/members", response_model=list[schemas.MemberOut])
def admin_list_members(
    db: Session = Depends(get_db),
    admin: models.Member = Depends(auth.require_admin),
):
    stmt = select(models.Member).order_by(func.coalesce(models.Member.full_name, "ZZZ"), models.Member.email)
    return db.scalars(stmt).all()


@app.post("/admin/members", response_model=schemas.MemberOut, status_code=201)
def admin_create_member(
    payload: schemas.MemberCreateIn,
    db: Session = Depends(get_db),
    admin: models.Member = Depends(auth.require_admin),
):
    if db.scalar(select(models.Member).where(models.Member.email == payload.email)):
        raise HTTPException(status_code=400, detail="Email already exists")

    member = models.Member(
        email=payload.email,
        hashed_password=auth.hash_password(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
        address=payload.address,
        member_since=payload.member_since,
        birthday=payload.birthday,
        is_admin=payload.is_admin,
        is_active=True,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


@app.patch("/admin/members/{member_id}", response_model=schemas.MemberOut)
def admin_update_member(
    member_id: int,
    payload: schemas.AdminMemberUpdateIn,
    db: Session = Depends(get_db),
    admin: models.Member = Depends(auth.require_admin),
):
    m = db.get(models.Member, member_id)
    if not m:
        raise HTTPException(status_code=404, detail="Member not found")

    if m.id == admin.id and payload.is_admin is False:
        raise HTTPException(status_code=400, detail="You cannot remove your own admin role")

    if payload.full_name is not None:
        m.full_name = payload.full_name
    if payload.phone is not None:
        m.phone = payload.phone
    if payload.address is not None:
        m.address = payload.address
    if payload.member_since is not None:
        m.member_since = payload.member_since
    if payload.birthday is not None:
        m.birthday = payload.birthday
    if payload.is_admin is not None:
        m.is_admin = payload.is_admin

    db.commit()
    db.refresh(m)
    return m


@app.patch("/admin/members/{member_id}/active", response_model=schemas.MemberOut)
def admin_set_member_active(
    member_id: int,
    payload: schemas.AdminMemberActiveIn,
    db: Session = Depends(get_db),
    admin: models.Member = Depends(auth.require_admin),
):
    m = db.get(models.Member, member_id)
    if not m:
        raise HTTPException(status_code=404, detail="Member not found")

    if m.id == admin.id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

    m.is_active = payload.is_active
    db.commit()
    db.refresh(m)
    return m


@app.patch("/admin/members/{member_id}/password", status_code=200)
def admin_reset_member_password(
    member_id: int,
    payload: schemas.AdminPasswordResetIn,
    db: Session = Depends(get_db),
    admin: models.Member = Depends(auth.require_admin),
):
    m = db.get(models.Member, member_id)
    if not m:
        raise HTTPException(status_code=404, detail="Member not found")

    m.hashed_password = auth.hash_password(payload.password)
    db.commit()
    return {"ok": True}


# -------------------------------------------------
# MEMBER PROFILE + ROSTER
# -------------------------------------------------
@app.get("/member/me", response_model=schemas.MemberOut)
def member_me(member: models.Member = Depends(auth.get_current_member)):
    return member


@app.put("/member/me", response_model=schemas.MemberOut)
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


@app.get("/member/roster", response_model=list[schemas.MemberOut])
def member_roster(
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    stmt = (
        select(models.Member)
        .where(models.Member.is_active == True)  # noqa: E712
        .order_by(func.coalesce(models.Member.full_name, "ZZZ"), models.Member.email)
    )
    return db.scalars(stmt).all()


# -------------------------------------------------
# REQUESTS (member)
# -------------------------------------------------
@app.get("/member/requests", response_model=list[schemas.RequestOut])
def member_list_requests(
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    stmt = select(models.Request)
    if status_filter:
        stmt = stmt.where(models.Request.status == status_filter)
    return db.scalars(stmt.order_by(models.Request.created_at.desc())).all()


@app.patch("/member/requests/{request_id}/review", response_model=schemas.RequestOut)
def member_review_request(
    request_id: int,
    payload: schemas.RequestReviewIn,
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    req = db.get(models.Request, request_id)
    if not req:
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

    # ✅ EMAIL NOTIFICATION (approve/deny only)
    if req.requester_email and req.status in ("APPROVED", "DENIED"):
        subject = f"London Lions Request #{req.id}: {req.status}"
        note = (req.decision_note or "").strip()

        body = (
            f"Hello {req.requester_name},\n\n"
            f"Your request (#{req.id}) has been {req.status}.\n\n"
            f"Category: {req.category}\n"
            f"Submitted: {req.created_at}\n\n"
            + (f"Decision note:\n{note}\n\n" if note else "")
            + "Thank you,\nLondon Lions\n"
        )

        ok = send_email_if_configured(req.requester_email, subject, body)
        if not ok:
            print("EMAIL NOT SENT (disabled/missing config/SMTP failed).")

    return req


# -------------------------------------------------
# EVENTS
# -------------------------------------------------
@app.get("/member/events", response_model=list[schemas.EventOut])
def member_list_events(
    include_past: bool = True,
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    now = datetime.utcnow()
    stmt = select(models.Event)
    if not include_past:
        stmt = stmt.where(models.Event.start_at >= now)
    return db.scalars(stmt.order_by(models.Event.start_at.asc())).all()


@app.post("/member/events", response_model=schemas.EventOut, status_code=201)
def member_create_event(
    payload: schemas.EventCreateIn,
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    ev = models.Event(**payload.dict(), created_by_member_id=member.id)
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


@app.put("/member/events/{event_id}", response_model=schemas.EventOut)
def member_update_event(
    event_id: int,
    payload: schemas.EventCreateIn,
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    ev = db.get(models.Event, event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")

    if (not member.is_admin) and (ev.created_by_member_id != member.id):
        raise HTTPException(status_code=403, detail="Not allowed to edit this event")

    ev.title = payload.title
    ev.description = payload.description
    ev.location = payload.location
    ev.start_at = payload.start_at
    ev.end_at = payload.end_at
    ev.is_public = payload.is_public

    db.commit()
    db.refresh(ev)
    return ev


@app.delete("/member/events/{event_id}", status_code=204)
def member_delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    ev = db.get(models.Event, event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")

    if (not member.is_admin) and (ev.created_by_member_id != member.id):
        raise HTTPException(status_code=403, detail="Not allowed to delete this event")

    db.delete(ev)
    db.commit()
    return


# -------------------------------------------------
# SERVICE HOURS
# -------------------------------------------------
@app.post("/member/service-hours", response_model=schemas.ServiceHourOut, status_code=201)
def member_log_service_hours(
    payload: schemas.ServiceHourCreateIn,
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    entry = models.ServiceHour(member_id=member.id, **payload.dict())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@app.get("/member/service-hours", response_model=list[schemas.ServiceHourOut])
def member_list_service_hours(
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    stmt = (
        select(models.ServiceHour)
        .where(models.ServiceHour.member_id == member.id)
        .order_by(models.ServiceHour.service_date.desc())
    )
    return db.scalars(stmt).all()


@app.patch("/member/service-hours/{entry_id}", response_model=schemas.ServiceHourOut)
def member_update_service_hours(
    entry_id: int,
    payload: schemas.ServiceHourUpdateIn,
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    entry = db.get(models.ServiceHour, entry_id)
    if not entry:
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


@app.delete("/member/service-hours/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def member_delete_service_hours(
    entry_id: int,
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    entry = db.get(models.ServiceHour, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Service hour entry not found")

    if entry.member_id != member.id:
        raise HTTPException(status_code=403, detail="Not allowed to delete this entry")

    db.delete(entry)
    db.commit()
    return


@app.get("/member/service-hours/summary")
def member_service_hours_summary(
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    year = datetime.utcnow().year

    club_ytd_hours = db.scalar(
        select(func.coalesce(func.sum(models.ServiceHour.hours), 0.0))
        .where(func.strftime("%Y", models.ServiceHour.service_date) == str(year))
    ) or 0.0

    return {"year": year, "club_ytd_hours": float(club_ytd_hours)}


# -------------------------------------------------
# DASHBOARD METRICS
# -------------------------------------------------
@app.get("/member/requests/summary")
def member_requests_summary(
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    rows_status = db.execute(
        select(models.Request.status, func.count(models.Request.id))
        .group_by(models.Request.status)
    ).all()

    rows_category = db.execute(
        select(models.Request.category, func.count(models.Request.id))
        .group_by(models.Request.category)
    ).all()

    return {
        "total": db.scalar(select(func.count(models.Request.id))) or 0,
        "by_status": dict(rows_status),
        "by_category": dict(rows_category),
    }


@app.get("/reports/status-counts")
def get_status_counts(
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    rows = db.execute(
        select(models.Request.status, func.count(models.Request.id))
        .group_by(models.Request.status)
    ).all()
    return dict(rows)
