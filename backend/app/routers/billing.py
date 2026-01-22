# app/routers/billing.py
from __future__ import annotations

from datetime import datetime
from typing import Optional
import os

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, auth
from app.trial_guard import (
    get_trial_info,
    is_club_active_for_app,
    start_trial_if_allowed,
    has_email_claimed_trial,
)

# ✅ All billing endpoints live under /billing
router = APIRouter(prefix="/billing", tags=["billing"])


# -----------------------------
# Billing feature flag
# -----------------------------
def _billing_enabled() -> bool:
    v = (os.getenv("BILLING_ENABLED") or "").strip().lower()
    # default = enabled unless explicitly false-like
    return v not in ("0", "false", "no", "off")


def _require_billing_enabled() -> None:
    if not _billing_enabled():
        raise HTTPException(status_code=503, detail="Billing disabled")


# -----------------------------
# Stripe config helpers
# -----------------------------
def _get_base_url() -> str:
    base = (os.getenv("APP_BASE_URL") or "").strip().rstrip("/")
    return base or "http://127.0.0.1:8000"


def _init_stripe() -> None:
    _require_billing_enabled()
    key = (os.getenv("STRIPE_SECRET_KEY") or "").strip()
    if not key:
        raise HTTPException(status_code=500, detail="Stripe not configured (missing STRIPE_SECRET_KEY)")
    stripe.api_key = key


def _webhook_secret() -> str:
    wh = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()
    if not wh:
        raise HTTPException(status_code=500, detail="Missing STRIPE_WEBHOOK_SECRET")
    return wh


def _price_id() -> str:
    pid = (os.getenv("STRIPE_PRICE_PRO_MONTHLY") or "").strip()
    if not pid:
        raise HTTPException(status_code=500, detail="Missing STRIPE_PRICE_PRO_MONTHLY")
    return pid


def _unix_to_dt(v: Optional[int]) -> Optional[datetime]:
    if not v:
        return None
    try:
        return datetime.utcfromtimestamp(int(v))
    except Exception:
        return None


def _set_club_plan_from_status(club: models.Club, sub_status: str) -> None:
    s = (sub_status or "").lower().strip() or "inactive"
    club.subscription_status = s

    if s in ("active", "trialing", "past_due"):
        club.plan = "PRO"
    else:
        club.plan = "FREE"


def _status_payload(db: Session, club: models.Club, owner_email: str | None = None) -> dict:
    plan = (getattr(club, "plan", "FREE") or "FREE").upper().strip()
    sub_status = getattr(club, "subscription_status", "inactive")

    trial = get_trial_info(db, club)
    allowed, info = is_club_active_for_app(db, club)

    owner_email_n = (owner_email or "").strip().lower()
    can_start = False
    if plan != "PRO" and trial.get("status") == "never" and owner_email_n:
        can_start = not has_email_claimed_trial(db, owner_email_n)

    return {
        "ok": True,
        "billing_enabled": _billing_enabled(),
        "club": {
            "id": club.id,
            "slug": club.slug,
            "name": club.name,
            "plan": plan,
            "subscription_status": sub_status,
            "stripe_customer_id": getattr(club, "stripe_customer_id", None),
            "stripe_subscription_id": getattr(club, "stripe_subscription_id", None),
            "current_period_end": (
                club.current_period_end.isoformat()
                if getattr(club, "current_period_end", None)
                else None
            ),
        },
        "trial": trial,
        "is_locked": not allowed,
        "can_start_trial": bool(can_start),
        "lock_reason": None if allowed else (info.get("trial", {}).get("status") or "expired"),
    }


# -----------------------------
# ✅ status endpoint (works even when billing is disabled)
# -----------------------------
@router.get("/status")
def billing_status(
    db: Session = Depends(get_db),
    member: models.Member = Depends(auth.get_current_member),
):
    club = db.get(models.Club, member.club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")

    return _status_payload(db, club, owner_email=getattr(member, "email", None))


# -----------------------------
# ✅ start trial (OWNER only) — works even when billing is disabled
# -----------------------------
@router.post("/start-trial")
def billing_start_trial(
    db: Session = Depends(get_db),
    owner: models.Member = Depends(auth.require_owner),
):
    club = db.get(models.Club, owner.club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")

    result = start_trial_if_allowed(db, club, owner_email=getattr(owner, "email", "") or "")
    if result.get("status") == "blocked":
        return {
            "ok": False,
            "code": result.get("reason", "TRIAL_BLOCKED"),
            "message": "Free trial already used for this email.",
            "trial": result,
            "billing_enabled": _billing_enabled(),
        }

    return _status_payload(db, club, owner_email=getattr(owner, "email", None))


# -----------------------------
# OWNER-only endpoints (Stripe) — disabled when BILLING_ENABLED=false
# -----------------------------
@router.get("/me")
def billing_me(
    db: Session = Depends(get_db),
    owner: models.Member = Depends(auth.require_owner),
):
    _init_stripe()

    club = db.get(models.Club, owner.club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")

    return {
        "ok": True,
        "billing_enabled": _billing_enabled(),
        "club": {
            "id": club.id,
            "slug": club.slug,
            "name": club.name,
            "plan": getattr(club, "plan", "FREE"),
            "subscription_status": getattr(club, "subscription_status", "inactive"),
            "stripe_customer_id": getattr(club, "stripe_customer_id", None),
            "stripe_subscription_id": getattr(club, "stripe_subscription_id", None),
            "current_period_end": (
                club.current_period_end.isoformat()
                if getattr(club, "current_period_end", None)
                else None
            ),
        },
    }


@router.post("/checkout")
def billing_checkout(
    db: Session = Depends(get_db),
    owner: models.Member = Depends(auth.require_owner),
):
    _init_stripe()

    club = db.get(models.Club, owner.club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")

    current_status = (getattr(club, "subscription_status", "") or "").lower()
    if current_status in ("active", "trialing"):
        raise HTTPException(status_code=400, detail="Subscription already active")

    base = _get_base_url()
    success_url = f"{base}/admin/tools?billing=success"
    cancel_url = f"{base}/admin/tools?billing=cancel"

    if not getattr(club, "stripe_customer_id", None):
        customer = stripe.Customer.create(
            name=club.name,
            metadata={"club_id": str(club.id), "club_slug": club.slug},
        )
        club.stripe_customer_id = customer["id"]
        db.commit()

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=club.stripe_customer_id,
        line_items=[{"price": _price_id(), "quantity": 1}],
        allow_promotion_codes=True,
        success_url=success_url,
        cancel_url=cancel_url,
        subscription_data={"metadata": {"club_id": str(club.id), "club_slug": club.slug}},
        metadata={"club_id": str(club.id), "club_slug": club.slug},
    )

    return {"ok": True, "billing_enabled": _billing_enabled(), "url": session["url"]}


@router.post("/portal")
def billing_portal(
    db: Session = Depends(get_db),
    owner: models.Member = Depends(auth.require_owner),
):
    _init_stripe()

    club = db.get(models.Club, owner.club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")

    if not getattr(club, "stripe_customer_id", None):
        raise HTTPException(status_code=400, detail="No Stripe customer for this club yet")

    base = _get_base_url()
    return_url = f"{base}/admin/tools?billing=portal_return"

    portal = stripe.billing_portal.Session.create(
        customer=club.stripe_customer_id,
        return_url=return_url,
    )

    return {"ok": True, "billing_enabled": _billing_enabled(), "url": portal["url"]}


# -----------------------------
# Webhook (public) — disabled when BILLING_ENABLED=false
# -----------------------------
@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    _init_stripe()
    wh_secret = _webhook_secret()

    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    if not sig:
        raise HTTPException(status_code=400, detail="Missing Stripe signature header")

    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=sig, secret=wh_secret)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature")

    etype = (event.get("type") or "").strip()
    obj = event.get("data", {}).get("object", {}) or {}

    def find_club_by_customer(customer_id: str) -> Optional[models.Club]:
        if not customer_id:
            return None
        return db.scalar(select(models.Club).where(models.Club.stripe_customer_id == customer_id))

    def find_club_by_metadata(md: dict) -> Optional[models.Club]:
        md = md or {}
        club_id = md.get("club_id")
        if club_id:
            try:
                return db.get(models.Club, int(club_id))
            except Exception:
                return None
        return None

    def find_club_fallback() -> Optional[models.Club]:
        customer_id = (obj.get("customer") or "").strip()
        club = find_club_by_customer(customer_id)
        if club:
            return club

        club = find_club_by_metadata(obj.get("metadata") or {})
        if club:
            return club

        sub_id = (obj.get("subscription") or "").strip()
        if sub_id:
            try:
                sub = stripe.Subscription.retrieve(sub_id)
                cust = (sub.get("customer") or "").strip()
                return find_club_by_customer(cust) or find_club_by_metadata(sub.get("metadata") or {})
            except Exception:
                return None

        return None

    club = find_club_fallback()
    if not club:
        return {"ok": True, "ignored": True, "type": etype}

    if etype in ("customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"):
        sub_id = obj.get("id")
        sub_status = obj.get("status") or "inactive"
        period_end_unix = obj.get("current_period_end")

        club.stripe_subscription_id = sub_id
        club.current_period_end = _unix_to_dt(period_end_unix)
        _set_club_plan_from_status(club, sub_status)

        customer_id = (obj.get("customer") or "").strip()
        if customer_id and not getattr(club, "stripe_customer_id", None):
            club.stripe_customer_id = customer_id

        db.commit()
        return {"ok": True}

    if etype == "checkout.session.completed":
        sub_id = (obj.get("subscription") or "").strip()
        customer_id = (obj.get("customer") or "").strip()

        if customer_id and not getattr(club, "stripe_customer_id", None):
            club.stripe_customer_id = customer_id

        if sub_id:
            club.stripe_subscription_id = sub_id
            try:
                sub = stripe.Subscription.retrieve(sub_id)
                club.current_period_end = _unix_to_dt(sub.get("current_period_end"))
                _set_club_plan_from_status(club, sub.get("status") or "inactive")
            except Exception:
                club.subscription_status = "unknown"

        db.commit()
        return {"ok": True}

    if etype in ("invoice.payment_failed", "invoice.payment_action_required"):
        club.subscription_status = "past_due"
        club.plan = "PRO"
        db.commit()
        return {"ok": True}

    if etype in ("invoice.paid", "invoice.payment_succeeded"):
        sub_id = (obj.get("subscription") or "").strip() or (getattr(club, "stripe_subscription_id", "") or "").strip()
        if sub_id:
            try:
                sub = stripe.Subscription.retrieve(sub_id)
                club.stripe_subscription_id = sub.get("id")
                club.current_period_end = _unix_to_dt(sub.get("current_period_end"))
                _set_club_plan_from_status(club, sub.get("status") or "inactive")
            except Exception:
                club.subscription_status = "active"
                club.plan = "PRO"
        else:
            club.subscription_status = "active"
            club.plan = "PRO"

        db.commit()
        return {"ok": True}

    return {"ok": True, "ignored": True, "type": etype}
