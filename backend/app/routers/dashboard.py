# app/routers/dashboard.py

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, auth

router = APIRouter(tags=["Dashboard"])


# -------------------------------------------------
# DASHBOARD METRICS (optional endpoint)
# -------------------------------------------------
# NOTE: You already have /member/requests/summary in main.py.
# This endpoint is fine to keep as a "router-style" option.
@router.get("/dashboard/metrics")
def get_dashboard_metrics(
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    results = (
        db.execute(
            select(models.Request.status, func.count(models.Request.id))
            .group_by(models.Request.status)
        )
        .all()
    )
    metrics = {status: count for status, count in results}
    return {"total": sum(metrics.values()), "by_status": metrics}


# -------------------------------------------------
# EVENTS: MEMBER LIST (THIS IS THE IMPORTANT ONE)
# -------------------------------------------------
@router.get("/member/events", response_model=list[schemas.EventOut])
def member_list_events(
    include_past: bool = Query(default=True, description="Include events in the past"),
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    """
    Member-only list of ALL events (public + private).
    """
    stmt = select(models.Event)

    if not include_past:
        now = datetime.utcnow()
        stmt = stmt.where(models.Event.start_at >= now)

    stmt = stmt.order_by(models.Event.start_at.asc())
    return db.scalars(stmt).all()
