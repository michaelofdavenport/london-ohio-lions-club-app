# app/routers/reports.py
from __future__ import annotations

from fastapi import APIRouter, Depends

from app import auth
from app.pro_guard import require_pro_club
from app.trial_guard import require_active_access


router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[
        Depends(auth.get_current_member),  # logged in
        Depends(require_active_access),    # ✅ Phase 4 hard-lock trial gate
        Depends(require_pro_club),         # PRO-only
    ],
)


@router.get("/ping")
def reports_ping():
    return {"ok": True, "reports": "enabled"}
