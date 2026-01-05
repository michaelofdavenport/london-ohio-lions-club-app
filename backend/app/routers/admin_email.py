# app/routers/admin_email.py

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import auth, models
from app.emailer import send_email_if_configured


router = APIRouter(prefix="/admin/email", tags=["admin-email"])


@router.post("/test")
def send_test_email(
    to_email: str | None = Query(None),
    db: Session = Depends(get_db),
    me: models.Member = Depends(auth.require_admin),
):
    """
    Sends a test email using your SMTP settings (.env).
    If `to_email` is not provided, it defaults to the current admin's email.
    Returns ok=True if the email was attempted+sent, ok=False if skipped/failed.
    """
    dest = (to_email or me.email or "").strip()

    subject = "London Lions Test Email"
    body = (
        f"Hello {me.full_name or me.email},\n\n"
        "✅ This is a test email from your London Lions app.\n\n"
        "If you received this, SMTP is configured correctly.\n\n"
        "— London Lions"
    )

    ok = send_email_if_configured(dest, subject, body)
    return {"ok": bool(ok), "to": dest}
