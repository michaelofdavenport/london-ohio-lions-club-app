# app/routers/admin_tools.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from app import auth, models
from app.trial_guard import require_active_access


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    # ✅ Phase 4 gate: must be logged in AND have active access (trial or PRO)
    dependencies=[
        Depends(auth.get_current_member),
        Depends(require_active_access),
    ],
)


@router.get("/tools", response_class=HTMLResponse)
def admin_tools_page() -> str:
    """
    Admin tools landing page.

    - Must be logged in
    - Must pass trial access gate (FREE trial OR PRO)
    - NOT PRO-only anymore (billing/upgrade UI lives here)
    """
    # This endpoint mainly exists so Stripe success/cancel URLs have somewhere to go.
    # Real UI is served from /static/admin_tools.html
    return """
    <html>
      <head>
        <meta charset="utf-8" />
        <title>Admin Tools</title>
        <meta http-equiv="refresh" content="0; url=/static/admin_tools.html" />
      </head>
      <body>
        <p>Redirecting to Admin Tools…</p>
        <p><a href="/static/admin_tools.html">Click here if you are not redirected</a></p>
      </body>
    </html>
    """


@router.get("/ping")
def admin_ping(member: models.Member = Depends(auth.get_current_member)):
    """
    Small context endpoint used by admin_tools.js to decide:
      - role (OWNER / ADMIN / MEMBER)
      - whether user is admin
    """
    # Adjust these field names if your model differs.
    # Most builds have: is_owner bool or role str, and is_admin bool.
    role = "MEMBER"
    if getattr(member, "is_owner", False):
        role = "OWNER"
    elif getattr(member, "is_admin", False):
        role = "ADMIN"

    return {
        "ok": True,
        "role": role,
        "is_admin": bool(getattr(member, "is_admin", False)),
        "is_owner": bool(getattr(member, "is_owner", False)),
        "member_id": member.id,
        "club_id": member.club_id,
        "email": getattr(member, "email", None),
    }
