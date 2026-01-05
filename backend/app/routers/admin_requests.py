# app/routers/admin_requests.py

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, auth
from app.emailer import send_email_if_configured

router = APIRouter(prefix="/admin/requests", tags=["admin-requests"])


# ----------------------------
# Schemas
# ----------------------------
class RequestOut(BaseModel):
    id: int
    category: str
    status: str

    requester_name: str
    requester_email: Optional[str] = None
    requester_phone: Optional[str] = None
    requester_address: Optional[str] = None

    description: str
    created_at: datetime

    assigned_to_member_id: Optional[int] = None
    assigned_at: Optional[datetime] = None

    reviewed_by_member_id: Optional[int] = None
    reviewed_by_name: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    decision_note: Optional[str] = None

    class Config:
        from_attributes = True


class DecisionIn(BaseModel):
    status: str = Field(pattern="^(APPROVED|DENIED)$")
    decision_note: Optional[str] = None


class StatusIn(BaseModel):
    # Matches your UI list; add/remove values as needed.
    status: str = Field(pattern="^(PENDING|IN_PROGRESS|CLOSED|APPROVED|DENIED)$")
    assigned_to_member_id: Optional[int] = None
    decision_note: Optional[str] = None


# ----------------------------
# Helpers
# ----------------------------
def get_request_or_404(db: Session, request_id: int) -> models.Request:
    req = db.get(models.Request, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    return req


def _reviewer_name(req: models.Request) -> Optional[str]:
    try:
        if getattr(req, "reviewed_by", None) is not None:
            return getattr(req.reviewed_by, "full_name", None) or getattr(req.reviewed_by, "email", None)
    except Exception:
        pass
    return None


def _maybe_notify_requester(req: models.Request) -> None:
    """Email requester if they provided an email. Never raises."""
    if not req.requester_email:
        return

    subject = f"London Lions – Your request #{req.id} is now {req.status}"
    body = (
        f"Hello {req.requester_name},\n\n"
        f"Your request #{req.id} ({req.category}) is now marked as: {req.status}\n\n"
        f"Note: {req.decision_note or '—'}\n\n"
        f"Thank you,\nLondon Lions"
    )
    send_email_if_configured(req.requester_email, subject, body)


# ----------------------------
# Endpoints
# ----------------------------
@router.get("", response_model=List[RequestOut])
def list_requests(
    status: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(300, ge=1, le=1000),
    db: Session = Depends(get_db),
    me: models.Member = Depends(auth.require_admin),
):
    qry = select(models.Request)

    if status:
        qry = qry.where(models.Request.status == status)

    if q:
        like = f"%{q.strip()}%"
        qry = qry.where(
            (models.Request.requester_name.ilike(like))
            | (models.Request.requester_email.ilike(like))
            | (models.Request.description.ilike(like))
        )

    reqs = db.scalars(qry.order_by(models.Request.id.desc()).limit(limit)).all()

    out: List[RequestOut] = []
    for r in reqs:
        out.append(
            RequestOut(
                id=r.id,
                category=r.category,
                status=r.status,
                requester_name=r.requester_name,
                requester_email=r.requester_email,
                requester_phone=r.requester_phone,
                requester_address=r.requester_address,
                description=r.description,
                created_at=r.created_at,
                assigned_to_member_id=getattr(r, "assigned_to_member_id", None),
                assigned_at=getattr(r, "assigned_at", None),
                reviewed_by_member_id=r.reviewed_by_member_id,
                reviewed_by_name=_reviewer_name(r),
                reviewed_at=r.reviewed_at,
                decision_note=r.decision_note,
            )
        )
    return out


@router.patch("/{request_id}/decision")
def decide_request(
    request_id: int,
    body: DecisionIn,
    db: Session = Depends(get_db),
    me: models.Member = Depends(auth.require_admin),
):
    req = get_request_or_404(db, request_id)

    req.status = body.status
    req.reviewed_by_member_id = me.id
    req.reviewed_at = datetime.utcnow()
    req.decision_note = body.decision_note
    if hasattr(req, "updated_at"):
        req.updated_at = datetime.utcnow()

    db.commit()

    # Optional: notify requester
    try:
        _maybe_notify_requester(req)
    except Exception:
        pass

    return {"ok": True}


# ✅ THIS is what your Inbox "Save Assign/Status" expects:
@router.patch("/{request_id}/status")
def update_status_and_assignment(
    request_id: int,
    body: StatusIn,
    db: Session = Depends(get_db),
    me: models.Member = Depends(auth.require_admin),
):
    req = get_request_or_404(db, request_id)

    # Status change
    req.status = body.status

    # Assignment change (optional)
    if hasattr(req, "assigned_to_member_id"):
        req.assigned_to_member_id = body.assigned_to_member_id
        if hasattr(req, "assigned_at"):
            req.assigned_at = datetime.utcnow() if body.assigned_to_member_id else None

    # Optional note
    if body.decision_note is not None:
        req.decision_note = body.decision_note

    # Auto-set closed_at if status CLOSED
    if hasattr(req, "closed_at"):
        req.closed_at = datetime.utcnow() if body.status == "CLOSED" else None

    if hasattr(req, "updated_at"):
        req.updated_at = datetime.utcnow()

    db.commit()

    return {"ok": True}


# ✅ CSV Export (Admin-only)
@router.get("/export.csv")
def export_requests_csv(
    status: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(2000, ge=1, le=10000),
    db: Session = Depends(get_db),
    me: models.Member = Depends(auth.require_admin),
):
    qry = select(models.Request)

    if status:
        qry = qry.where(models.Request.status == status)

    if q:
        like = f"%{q.strip()}%"
        qry = qry.where(
            (models.Request.requester_name.ilike(like))
            | (models.Request.requester_email.ilike(like))
            | (models.Request.description.ilike(like))
        )

    reqs = db.scalars(qry.order_by(models.Request.id.desc()).limit(limit)).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "category",
            "status",
            "requester_name",
            "requester_email",
            "requester_phone",
            "requester_address",
            "description",
            "created_at",
            "assigned_to_member_id",
            "assigned_at",
            "reviewed_by_member_id",
            "reviewed_at",
            "decision_note",
        ]
    )

    for r in reqs:
        writer.writerow(
            [
                r.id,
                r.category,
                r.status,
                r.requester_name,
                r.requester_email or "",
                r.requester_phone or "",
                r.requester_address or "",
                (r.description or "").replace("\n", " ").strip(),
                r.created_at.isoformat() if r.created_at else "",
                getattr(r, "assigned_to_member_id", "") or "",
                getattr(r, "assigned_at", None).isoformat() if getattr(r, "assigned_at", None) else "",
                r.reviewed_by_member_id or "",
                r.reviewed_at.isoformat() if r.reviewed_at else "",
                (r.decision_note or "").replace("\n", " ").strip(),
            ]
        )

    buf.seek(0)

    filename = f"london_lions_requests_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers=headers)
