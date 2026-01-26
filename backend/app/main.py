# backend/app/main.py
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
import os

from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.database import Base, engine, get_db
from app import models, schemas, auth
from app.emailer import send_email_if_configured

# ✅ IMPORTANT: preserve real HTTP codes + catch true 500s
from app.authz_errors import http_exception_handler, unhandled_exception_handler

# ✅ Phase 3A: standardized email templates
from app.email_templates import request_received, admin_new_request

# Routers
from app.routers import dashboard
from app.routers import admin_requests
from app.routers import admin_email
from app.routers import admin_events
from app.routers import billing
from app.routers import admin_tools
from app.routers import reports
from app.routers import billing_status
from app.routers import setup
from app.routers import demo
from app.routers import member
import app.routers.public_club as public_club
from app.routers import admin_club
from app.routers import admin_ping

# ✅ Phase 3 modular routers
from app.routers import admin_members
from app.routers import owner
from app.routers import super_admin

# ✅ Bootstrap router
from app.bootstrap import router as bootstrap_router


# -------------------------------------------------
# LOAD .env ONCE (top of file, before any getenv use)
# -------------------------------------------------
_env_path = find_dotenv(usecwd=True)
load_dotenv(_env_path, override=True)

if (os.getenv("DEBUG_ENV") or "").strip().lower() in ("1", "true", "yes", "on"):
    print("DOTENV PATH =", _env_path)
    print("SMTP_HOST =", os.getenv("SMTP_HOST"))
    print("SMTP_USERNAME =", os.getenv("SMTP_USERNAME"))

APP_BASE_URL = (os.getenv("APP_BASE_URL") or "").strip()


# -------------------------------------------------
# EMAIL TIME HELPERS (US/Eastern for ALL emails)
# NO ZoneInfo / NO tzdata (Windows-safe)
# -------------------------------------------------
def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> datetime:
    first = datetime(year, month, 1)
    delta_days = (weekday - first.weekday()) % 7
    day = 1 + delta_days + (n - 1) * 7
    return datetime(year, month, day)


def _first_weekday_of_month(year: int, month: int, weekday: int) -> datetime:
    return _nth_weekday_of_month(year, month, weekday, 1)


def _us_eastern_dst_range_utc(year: int) -> tuple[datetime, datetime]:
    dst_start_local = _nth_weekday_of_month(year, 3, weekday=6, n=2).replace(
        hour=2, minute=0, second=0, microsecond=0
    )
    dst_start_utc = dst_start_local + timedelta(hours=5)

    dst_end_local = _first_weekday_of_month(year, 11, weekday=6).replace(
        hour=2, minute=0, second=0, microsecond=0
    )
    dst_end_utc = dst_end_local + timedelta(hours=4)

    return dst_start_utc, dst_end_utc


def _is_us_eastern_dst(utc_dt: datetime) -> bool:
    dst_start_utc, dst_end_utc = _us_eastern_dst_range_utc(utc_dt.year)
    return dst_start_utc <= utc_dt < dst_end_utc


def _utc_naive_to_eastern(utc_naive: datetime) -> datetime:
    if _is_us_eastern_dst(utc_naive):
        return utc_naive - timedelta(hours=4)
    return utc_naive - timedelta(hours=5)


def _parse_utc_naive(utc_naive: Optional[str]) -> Optional[datetime]:
    if not utc_naive:
        return None
    try:
        return datetime.fromisoformat(str(utc_naive).strip())
    except Exception:
        return None


def _fmt_eastern_from_utc_naive_dt(dt_utc_naive: Optional[datetime]) -> str:
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

# ✅ Preserve real HTTP errors (401/403/404/etc)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)

# ✅ Only true “unexpected errors” become 500 in a controlled way
app.add_exception_handler(Exception, unhandled_exception_handler)

# ✅ Trial guard middleware (optional safe import)
try:
    from app.trial_guard import TrialGuardMiddleware  # type: ignore

    app.add_middleware(TrialGuardMiddleware)
except Exception:
    # If middleware name/path differs, don't crash startup.
    pass

app.mount("/static", StaticFiles(directory="app/static"), name="static")


# -------------------------------------------------
# ✅ CONTRACT-FIRST ROUTE MAP (SAFE)
# View all paths + methods the server actually exposes.
# Requires login so we don't leak internals publicly.
# -------------------------------------------------
from fastapi.routing import APIRoute  # noqa: E402


@app.get("/__routes")
def __routes(_member=Depends(auth.get_current_member)):
    out = []
    for r in app.routes:
        if isinstance(r, APIRoute):
            out.append({"path": r.path, "methods": sorted(list(r.methods or [])), "name": r.name})
    return out


@app.get("/static/admin_tools.html")
def block_admin_tools_direct():
    raise HTTPException(status_code=404, detail="Not found")


# -------------------------------------------------
# Routers
# -------------------------------------------------
app.include_router(dashboard.router)
app.include_router(admin_requests.router)
app.include_router(admin_email.router)
app.include_router(admin_events.router)
app.include_router(billing.router)
app.include_router(admin_tools.router)
app.include_router(reports.router)
app.include_router(billing_status.router)
app.include_router(setup.router)
app.include_router(demo.router)
app.include_router(public_club.router)
app.include_router(admin_club.router)
app.include_router(member.router)
app.include_router(admin_ping.router)
app.include_router(bootstrap_router)
app.include_router(member.admin_router)

# ✅ Phase 3 modular routers
app.include_router(admin_members.router)
app.include_router(owner.router)
app.include_router(super_admin.router)


# -------------------------------------------------
# ROOT + HEALTH + VERSION
# -------------------------------------------------
@app.get("/")
def root():
    return RedirectResponse(url="/static/public_request.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {
        "name": app.title,
        "version": app.version,
        "build_date": os.getenv("BUILD_DATE", "unknown"),
        "git_sha": os.getenv("GIT_SHA", "unknown"),
    }


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


def _ensure_default_club(db: Session) -> models.Club:
    club = db.scalar(select(models.Club).where(models.Club.slug == "london-ohio"))
    if club:
        return club

    any_club = db.scalar(select(models.Club).limit(1))
    if any_club:
        return any_club

    club = models.Club(
        slug="london-ohio",
        name="London Ohio Lions Club",
        logo_url="/static/images/lions_emblem.png",
        is_active=True,
    )
    db.add(club)
    db.commit()
    db.refresh(club)
    return club


def _backfill_club_ids(db: Session, default_club_id: int) -> None:
    try:
        db.execute(text("UPDATE members SET club_id = :cid WHERE club_id IS NULL"), {"cid": default_club_id})
        db.execute(text("UPDATE requests SET club_id = :cid WHERE club_id IS NULL"), {"cid": default_club_id})
        db.execute(text("UPDATE events SET club_id = :cid WHERE club_id IS NULL"), {"cid": default_club_id})
        db.execute(text("UPDATE service_hours SET club_id = :cid WHERE club_id IS NULL"), {"cid": default_club_id})
        db.commit()
    except Exception:
        db.rollback()


def _backfill_member_roles(db: Session) -> None:
    try:
        db.execute(
            text(
                """
                UPDATE members
                SET role = 'MEMBER'
                WHERE role IS NULL OR TRIM(role) = ''
                """
            )
        )

        db.execute(
            text(
                """
                UPDATE members
                SET role = 'ADMIN'
                WHERE is_admin = 1
                  AND (role IS NULL OR TRIM(role) = '' OR role = 'MEMBER')
                """
            )
        )

        db.execute(
            text(
                """
                UPDATE members
                SET role = 'OWNER'
                WHERE is_super_admin = 1
                """
            )
        )

        db.commit()
    except Exception:
        db.rollback()


@app.on_event("startup")
def bootstrap_startup():
    db = next(get_db())
    try:
        _sqlite_add_column_if_missing(db, "members", "member_since", "DATE")
        _sqlite_add_column_if_missing(db, "members", "birthday", "DATE")

        _sqlite_add_column_if_missing(db, "requests", "assigned_to_member_id", "INTEGER")
        _sqlite_add_column_if_missing(db, "requests", "assigned_at", "DATETIME")
        _sqlite_add_column_if_missing(db, "requests", "closed_at", "DATETIME")
        _sqlite_add_column_if_missing(db, "requests", "priority", "TEXT")
        _sqlite_add_column_if_missing(db, "requests", "updated_at", "DATETIME")

        _sqlite_add_column_if_missing(db, "members", "club_id", "INTEGER")
        _sqlite_add_column_if_missing(db, "requests", "club_id", "INTEGER")
        _sqlite_add_column_if_missing(db, "events", "club_id", "INTEGER")
        _sqlite_add_column_if_missing(db, "service_hours", "club_id", "INTEGER")

        _sqlite_add_column_if_missing(db, "members", "is_super_admin", "BOOLEAN DEFAULT 0")
        _sqlite_add_column_if_missing(db, "members", "role", "TEXT DEFAULT 'MEMBER'")

        _sqlite_add_column_if_missing(db, "clubs", "plan", "TEXT DEFAULT 'FREE'")
        _sqlite_add_column_if_missing(db, "clubs", "subscription_status", "TEXT DEFAULT 'inactive'")
        _sqlite_add_column_if_missing(db, "clubs", "stripe_customer_id", "TEXT")
        _sqlite_add_column_if_missing(db, "clubs", "stripe_subscription_id", "TEXT")
        _sqlite_add_column_if_missing(db, "clubs", "current_period_end", "DATETIME")

        # -------------------------------------------------
        # ✅ Phase 4 (Option B): one-time-per-email free trial ledger
        # -------------------------------------------------
        try:
            db.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS trial_redemptions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        email_normalized TEXT NOT NULL UNIQUE,
                        redeemed_at DATETIME NOT NULL
                    );
                    """
                )
            )
            db.commit()
        except Exception:
            db.rollback()

        default_club = _ensure_default_club(db)
        _backfill_club_ids(db, default_club.id)
        _backfill_member_roles(db)

        seed_admin = (os.getenv("SEED_ADMIN") or "").strip().lower() in ("1", "true", "yes", "on")
        if seed_admin:
            admin_exists = db.scalar(select(models.Member).where(models.Member.is_admin == True))  # noqa: E712
            if not admin_exists:
                admin_email = (os.getenv("SEED_ADMIN_EMAIL") or "admin@example.com").strip().lower()
                admin_password = (os.getenv("SEED_ADMIN_PASSWORD") or "AdminPassword123!").strip()

                admin_user = models.Member(
                    email=admin_email,
                    hashed_password=auth.hash_password(admin_password),
                    full_name="Default Admin",
                    is_admin=True,
                    is_active=True,
                    club_id=default_club.id,
                    role="ADMIN",
                )
                db.add(admin_user)
                db.commit()

        seed_super = (os.getenv("SEED_SUPER_ADMIN") or "").strip().lower() in ("1", "true", "yes", "on")
        if seed_super:
            super_exists = db.scalar(select(models.Member).where(models.Member.is_super_admin == True))  # noqa: E712
            if not super_exists:
                super_email = (os.getenv("SEED_SUPER_ADMIN_EMAIL") or "superadmin@example.com").strip().lower()
                super_password = (os.getenv("SEED_SUPER_ADMIN_PASSWORD") or "SuperAdminPassword123!").strip()

                super_user = models.Member(
                    email=super_email,
                    hashed_password=auth.hash_password(super_password),
                    full_name="Platform Super Admin",
                    is_admin=True,
                    is_active=True,
                    club_id=default_club.id,
                    role="OWNER",
                    is_super_admin=True,
                )
                db.add(super_user)
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
    email = (form_data.username or "").strip().lower()
    password = form_data.password or ""

    member_obj = db.scalar(select(models.Member).where(models.Member.email == email))
    if not member_obj or not auth.verify_password(password, member_obj.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not member_obj.is_active:
        raise HTTPException(status_code=403, detail="Member is inactive")

    if not member_obj.club_id:
        raise HTTPException(status_code=500, detail="Member missing club_id")

    token = auth.create_access_token(
        subject=member_obj.email,
        member_id=member_obj.id,
        club_id=member_obj.club_id,
        is_admin=bool(member_obj.is_admin),
        is_super_admin=bool(getattr(member_obj, "is_super_admin", False)),
        role=getattr(member_obj, "role", None),
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "club_id": int(member_obj.club_id),
        "member_id": int(member_obj.id),
        "is_admin": bool(member_obj.is_admin),
        "is_super_admin": bool(getattr(member_obj, "is_super_admin", False)),
        "role": getattr(member_obj, "role", None),
    }


# -------------------------------------------------
# SaaS PUBLIC: club info + club-scoped request submit
# -------------------------------------------------
class PublicRequestSaaSIn(BaseModel):
    request_type: str
    name: str
    phone: str = ""
    email: str = ""
    address: str = ""
    details: str = ""


@app.get("/public/{club_slug}/info")
def public_club_info(club_slug: str, db: Session = Depends(get_db)):
    club = db.scalar(
        select(models.Club).where(
            models.Club.slug == club_slug,
            models.Club.is_active == True,  # noqa: E712
        )
    )
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")

    return {
        "slug": club.slug,
        "name": club.name,
        "logo_url": club.logo_url or "/static/images/lions_emblem.png",
        "subtitle": "Public Request Form",
    }


@app.post("/public/{club_slug}/request", status_code=201)
def public_create_request_saas(club_slug: str, payload: PublicRequestSaaSIn, db: Session = Depends(get_db)):
    club = db.scalar(
        select(models.Club).where(
            models.Club.slug == club_slug,
            models.Club.is_active == True,  # noqa: E712
        )
    )
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")

    req = models.Request(
        club_id=club.id,
        category=(payload.request_type or "").strip(),
        requester_name=(payload.name or "").strip(),
        requester_phone=(payload.phone or "").strip() or None,
        requester_email=(payload.email or "").strip() or None,
        requester_address=(payload.address or "").strip() or None,
        description=(payload.details or "").strip(),
        status="PENDING",
        updated_at=datetime.utcnow(),
    )

    if not req.category:
        raise HTTPException(status_code=400, detail="Missing request_type")
    if not req.requester_name:
        raise HTTPException(status_code=400, detail="Missing name")
    if not (req.requester_phone or ""):
        raise HTTPException(status_code=400, detail="Missing phone")
    if not (req.requester_address or ""):
        raise HTTPException(status_code=400, detail="Missing address")
    if not req.description:
        raise HTTPException(status_code=400, detail="Missing details")

    db.add(req)
    db.commit()
    db.refresh(req)

    if req.requester_email:
        parts = request_received(
            org_name=club.name,
            request_id=req.id,
            category=req.category,
            status=req.status,
            requester_name=req.requester_name,
            base_url=APP_BASE_URL,
        )
        ok = send_email_if_configured(req.requester_email, parts.subject, parts.body)
        if not ok:
            print("EMAIL RECEIPT NOT SENT (disabled/missing config/SMTP failed).")

    admin_to = (os.getenv("ADMIN_NOTIFY_EMAIL") or os.getenv("SMTP_FROM_EMAIL") or "").strip()
    if admin_to:
        parts = admin_new_request(
            org_name=club.name,
            club_slug=club.slug,
            request_id=req.id,
            category=req.category,
            requester_name=req.requester_name,
            requester_email=req.requester_email,
            requester_phone=req.requester_phone,
            requester_address=req.requester_address,
            description=req.description,
            base_url=APP_BASE_URL,
        )
        ok = send_email_if_configured(admin_to, parts.subject, parts.body)
        if not ok:
            print("EMAIL ADMIN NOTIFY NOT SENT (disabled/missing config/SMTP failed).")

    return {"ok": True, "request_id": req.id, "club_slug": club.slug}


@app.post("/public/requests", response_model=schemas.RequestOut, status_code=201)
def public_create_request(payload: schemas.PublicRequestCreate, db: Session = Depends(get_db)):
    default_club = db.scalar(select(models.Club).where(models.Club.slug == "london-ohio"))
    default_club_id = default_club.id if default_club else None

    req = models.Request(
        club_id=default_club_id,
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

    if req.requester_email:
        parts = request_received(
            org_name="London Lions Club",
            request_id=req.id,
            category=req.category,
            status=req.status,
            requester_name=req.requester_name,
            base_url=APP_BASE_URL,
        )
        ok = send_email_if_configured(req.requester_email, parts.subject, parts.body)
        if not ok:
            print("EMAIL RECEIPT NOT SENT (disabled/missing config/SMTP failed).")

    admin_to = (os.getenv("ADMIN_NOTIFY_EMAIL") or os.getenv("SMTP_FROM_EMAIL") or "").strip()
    if admin_to:
        parts = admin_new_request(
            org_name="London Lions Club",
            club_slug="london-ohio",
            request_id=req.id,
            category=req.category,
            requester_name=req.requester_name,
            requester_email=req.requester_email,
            requester_phone=req.requester_phone,
            requester_address=req.requester_address,
            description=req.description,
            base_url=APP_BASE_URL,
        )
        ok = send_email_if_configured(admin_to, parts.subject, parts.body)
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
