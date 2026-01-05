# app/routers/admin_events.py
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, auth
from app.emailer import send_email_if_configured

router = APIRouter(prefix="/admin/events", tags=["admin-events"])


# ------------------------------------------------------------
# EASTERN TIME (NO ZoneInfo / NO tzdata)
# ------------------------------------------------------------
# DB stores datetimes as UTC-naive (e.g., 2026-01-07 00:30:00)
# Convert to US Eastern with DST rules:
# - DST starts: 2nd Sunday in March at 2:00 AM local
# - DST ends:   1st Sunday in November at 2:00 AM local
# ------------------------------------------------------------

def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> datetime:
    """weekday: Monday=0 ... Sunday=6"""
    first = datetime(year, month, 1)
    delta_days = (weekday - first.weekday()) % 7
    day = 1 + delta_days + (n - 1) * 7
    return datetime(year, month, day)


def _us_eastern_dst_range_utc(year: int) -> tuple[datetime, datetime]:
    """
    Returns DST start/end instants in UTC for US Eastern time for given year.
    DST start: 2nd Sunday in March at 2:00 AM local (EST, UTC-5) -> 07:00 UTC
    DST end:   1st Sunday in Nov   at 2:00 AM local (EDT, UTC-4) -> 06:00 UTC
    """
    dst_start_local = _nth_weekday_of_month(year, 3, weekday=6, n=2).replace(
        hour=2, minute=0, second=0, microsecond=0
    )
    dst_start_utc = dst_start_local + timedelta(hours=5)

    dst_end_local = _nth_weekday_of_month(year, 11, weekday=6, n=1).replace(
        hour=2, minute=0, second=0, microsecond=0
    )
    dst_end_utc = dst_end_local + timedelta(hours=4)

    return dst_start_utc, dst_end_utc


def _is_us_eastern_dst(utc_dt: datetime) -> bool:
    dst_start_utc, dst_end_utc = _us_eastern_dst_range_utc(utc_dt.year)
    return dst_start_utc <= utc_dt < dst_end_utc


def _utc_naive_to_eastern(utc_naive: datetime) -> datetime:
    """Convert UTC-naive -> Eastern local naive."""
    return utc_naive - timedelta(hours=4) if _is_us_eastern_dst(utc_naive) else utc_naive - timedelta(hours=5)


def _fmt_et(dt: Optional[datetime]) -> str:
    """MM/DD/YYYY at h:mm AM/PM (ET)"""
    if not dt:
        return "—"

    utc_dt = dt.replace(tzinfo=None)  # treat as UTC-naive
    et = _utc_naive_to_eastern(utc_dt)

    mm = et.strftime("%m")
    dd = et.strftime("%d")
    yyyy = et.strftime("%Y")
    hour_12 = et.strftime("%I").lstrip("0") or "12"
    minute = et.strftime("%M")
    ampm = et.strftime("%p")

    return f"{mm}/{dd}/{yyyy} at {hour_12}:{minute} {ampm} (ET)"


def _fmt_range_et(start: Optional[datetime], end: Optional[datetime]) -> str:
    if not start:
        return "—"
    if not end:
        return _fmt_et(start)
    return f"{_fmt_et(start)} \u2192 {_fmt_et(end)}"


# ------------------------------------------------------------
# ROUTE: INVITE MEMBERS
# ------------------------------------------------------------
@router.post("/{event_id}/invite")
def invite_members_to_event(
    event_id: int,
    db: Session = Depends(get_db),
    admin: models.Member = Depends(auth.require_admin),
):
    ev = db.get(models.Event, event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")

    members = db.scalars(select(models.Member).where(models.Member.is_active == True)).all()  # noqa: E712

    recipients: list[str] = []
    for m in members:
        email = (getattr(m, "email", None) or "").strip()
        if email:
            recipients.append(email)

    if not recipients:
        return {"ok": True, "sent": 0, "failed": 0, "skipped": len(members), "event_id": ev.id}

    subject = f"London Lions – Event Reminder: {ev.title}"
    when_line = _fmt_range_et(getattr(ev, "start_at", None), getattr(ev, "end_at", None))

    body_base = (
        "Hello,\n\n"
        "This is a reminder about an upcoming London Lions event:\n\n"
        f"Title: {ev.title}\n"
        f"When: {when_line}\n"
        f"Location: {ev.location or '—'}\n\n"
        + (f"Details:\n{ev.description}\n\n" if ev.description else "")
        + "Thank you,\n"
        "London Lions\n"
    )

    sent = 0
    failed = 0

    for email in recipients:
        if send_email_if_configured(email, subject, body_base):
            sent += 1
        else:
            failed += 1

    return {
        "ok": True,
        "event_id": ev.id,
        "sent": sent,
        "failed": failed,
        "skipped": max(0, len(members) - len(recipients)),
    }
