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
# Schemas (response + inputs)
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
    assigned_to_name: Optional[str] = None  # used by inbox.js

    reviewed_by_member_id: Optional[int] = None
    reviewed_by_name: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    decision_note: Optional[str] = None

    class Config:
        from_attributes = True


class DecisionIn(BaseModel):
    status: str = Field(pattern="^(APPROVED|DENIED)$")
    decision_note: Optional[str] = None


# ✅ UPDATED: status endpoint can also accept assignment
class StatusIn(BaseModel):
    status: str = Field(pattern="^(PENDING|IN_PROGRESS|CLOSED|APPROVED|DENIED)$")
    assigned_to_member_id: Optional[int] = None


class AssignIn(BaseModel):
    assigned_to_member_id: Optional[int] = None


class NoteIn(BaseModel):
    note: str


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
            return req.reviewed_by.full_name or req.reviewed_by.email
    except Exception:
        pass
    return None


def _assignee_name(db: Session, assigned_to_member_id: Optional[int]) -> Optional[str]:
    if not assigned_to_member_id:
        return None
    m = db.get(models.Member, assigned_to_member_id)
    if not m:
        return None
    return m.full_name or m.email


def _notes_for_email(db: Session, request_id: int) -> List[models.RequestNote]:
    return (
        db.query(models.RequestNote)
        .filter(models.RequestNote.request_id == request_id)
        .order_by(models.RequestNote.created_at.desc())
        .all()
    )


def _format_notes_block(notes: List[models.RequestNote]) -> str:
    if not notes:
        return "— (no notes yet)"
    lines: List[str] = []
    for n in notes:
        when = n.created_at.strftime("%Y-%m-%d %H:%M") if n.created_at else ""
        who = ""
        try:
            if n.author:
                who = (n.author.full_name or n.author.email or "").strip()
        except Exception:
            who = ""
        header = f"{when} — {who}".strip(" —")
        lines.append(f"- {header}\n  {n.note}")
    return "\n".join(lines)


def _send_assignment_email(
    db: Session,
    req: models.Request,
    assignee: models.Member,
) -> None:
    """
    Sends an email to the assignee with request details + all notes.
    Never raises (safe).
    """
    to_email = (assignee.email or "").strip()
    if not to_email:
        return

    notes = _notes_for_email(db, req.id)
    notes_block = _format_notes_block(notes)

    subject = f"London Lions – New Assignment: Request #{req.id} ({req.category})"

    body = (
        f"Hello {assignee.full_name or assignee.email},\n\n"
        f"You have been assigned a new request.\n\n"
        f"Request ID: {req.id}\n"
        f"Category: {req.category}\n"
        f"Status: {req.status}\n"
        f"Submitted: {req.created_at}\n\n"
        f"Requester Name: {req.requester_name}\n"
        f"Requester Email: {req.requester_email or '—'}\n"
        f"Requester Phone: {req.requester_phone or '—'}\n"
        f"Requester Address: {req.requester_address or '—'}\n\n"
        f"Description:\n{req.description}\n\n"
        f"Notes (latest first):\n{notes_block}\n\n"
        f"Thank you,\nLondon Lions\n"
    )

    send_email_if_configured(to_email, subject, body)


# ----------------------------
# Endpoints
# ----------------------------

@router.get("", response_model=List[RequestOut])
def list_requests(
    status: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    assigned: Optional[str] = Query(None),  # "assigned" | "unassigned"
    limit: int = Query(300, ge=1, le=1000),
    db: Session = Depends(get_db),
    me: models.Member = Depends(auth.require_admin),
):
    qry = select(models.Request)

    if status:
        qry = qry.where(models.Request.status == status)

    if assigned == "assigned":
        qry = qry.where(models.Request.assigned_to_member_id.is_not(None))
    elif assigned == "unassigned":
        qry = qry.where(models.Request.assigned_to_member_id.is_(None))

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
                assigned_to_member_id=r.assigned_to_member_id,
                assigned_at=r.assigned_at,
                assigned_to_name=_assignee_name(db, r.assigned_to_member_id),
                reviewed_by_member_id=r.reviewed_by_member_id,
                reviewed_by_name=_reviewer_name(r),
                reviewed_at=r.reviewed_at,
                decision_note=r.decision_note,
            )
        )
    return out


@router.get("/{request_id}/notes")
def list_notes(
    request_id: int,
    db: Session = Depends(get_db),
    me: models.Member = Depends(auth.require_admin),
):
    _ = get_request_or_404(db, request_id)

    notes = (
        db.query(models.RequestNote)
        .filter(models.RequestNote.request_id == request_id)
        .order_by(models.RequestNote.created_at.desc())
        .all()
    )

    return [
        {
            "id": n.id,
            "request_id": n.request_id,
            "author_id": n.author_id,
            "author_name": (n.author.full_name or n.author.email) if n.author else None,
            "created_at": n.created_at.strftime("%Y-%m-%d %H:%M") if n.created_at else "",
            "note": n.note,
        }
        for n in notes
    ]


@router.post("/{request_id}/note")
def add_note(
    request_id: int,
    body: NoteIn,
    db: Session = Depends(get_db),
    me: models.Member = Depends(auth.require_admin),
):
    _ = get_request_or_404(db, request_id)

    note = (body.note or "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="Note is required")

    n = models.RequestNote(
        request_id=request_id,
        author_id=me.id,
        note=note,
        created_at=datetime.utcnow(),
    )
    db.add(n)

    req = db.get(models.Request, request_id)
    if req:
        req.updated_at = datetime.utcnow()

    db.commit()
    return {"ok": True}


@router.patch("/{request_id}/assign")
def assign_request(
    request_id: int,
    body: AssignIn,
    db: Session = Depends(get_db),
    me: models.Member = Depends(auth.require_admin),
):
    req = get_request_or_404(db, request_id)

    previous_assignee = req.assigned_to_member_id
    new_assignee_id = body.assigned_to_member_id

    assignee: Optional[models.Member] = None
    if new_assignee_id is not None:
        assignee = db.get(models.Member, new_assignee_id)
        if not assignee:
            raise HTTPException(status_code=400, detail="Assigned member not found")
        if not assignee.is_active:
            raise HTTPException(status_code=400, detail="Assigned member is inactive")

    req.assigned_to_member_id = new_assignee_id
    req.assigned_at = datetime.utcnow() if new_assignee_id else None
    req.updated_at = datetime.utcnow()

    db.commit()

    # ✅ Send email ONLY when assignment changes to a real person
    if new_assignee_id and new_assignee_id != previous_assignee and assignee:
        try:
            _send_assignment_email(db, req, assignee)
        except Exception:
            pass

    return {"ok": True}


@router.patch("/{request_id}/status")
def update_status(
    request_id: int,
    body: StatusIn,
    db: Session = Depends(get_db),
    me: models.Member = Depends(auth.require_admin),
):
    req = get_request_or_404(db, request_id)

    # Track previous assignment for email logic
    previous_assignee = req.assigned_to_member_id
    new_assignee_id = body.assigned_to_member_id

    # Validate assignee if provided (including explicit unassign via null)
    assignee: Optional[models.Member] = None
    if new_assignee_id is not None:
        assignee = db.get(models.Member, new_assignee_id)
        if not assignee:
            raise HTTPException(status_code=400, detail="Assigned member not found")
        if not assignee.is_active:
            raise HTTPException(status_code=400, detail="Assigned member is inactive")

    # Apply updates
    req.status = body.status
    req.closed_at = datetime.utcnow() if body.status == "CLOSED" else None

    # Only touch assignment fields if assigned_to_member_id was included in payload
    # (Pydantic will include it even if null; your UI sends null for Unassigned)
    req.assigned_to_member_id = new_assignee_id
    req.assigned_at = datetime.utcnow() if new_assignee_id else None

    req.updated_at = datetime.utcnow()
    db.commit()

    email_sent = False
    email_error: Optional[str] = None

    # ✅ Send email ONLY when assignment changes to a real person
    if new_assignee_id and new_assignee_id != previous_assignee and assignee:
        try:
            _send_assignment_email(db, req, assignee)
            email_sent = True
        except Exception as e:
            email_error = str(e)

    # Return extra info (frontend can ignore, or display)
    return {"ok": True, "email_sent": email_sent, "email_error": email_error}


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
    req.updated_at = datetime.utcnow()

    db.commit()

    # Optional notify requester
    if req.requester_email:
        try:
            subject = f"London Lions – Your request #{req.id} is now {req.status}"
            msg = (
                f"Hello {req.requester_name},\n\n"
                f"Your request #{req.id} ({req.category}) is now marked as: {req.status}\n\n"
                f"Note: {req.decision_note or '—'}\n\n"
                f"Thank you,\nLondon Lions"
            )
            send_email_if_configured(req.requester_email, subject, msg)
        except Exception:
            pass

    return {"ok": True}


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
                r.assigned_to_member_id or "",
                r.assigned_at.isoformat() if r.assigned_at else "",
                r.reviewed_by_member_id or "",
                r.reviewed_at.isoformat() if r.reviewed_at else "",
                (r.decision_note or "").replace("\n", " ").strip(),
            ]
        )

    buf.seek(0)

    filename = f"london_lions_requests_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers=headers)
