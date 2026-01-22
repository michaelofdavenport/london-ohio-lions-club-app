# app/plans.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

PLAN_FREE = "FREE"
PLAN_PRO = "PRO"

FEATURE_PRO_REPORTS = "PRO_REPORTS"
FEATURE_PRO_ADMIN_TOOLS = "PRO_ADMIN_TOOLS"
FEATURE_PRO_EXPORTS = "PRO_EXPORTS"

DEFAULT_TRIAL_DAYS = 14


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    reason: str = ""          # e.g. "trial_expired"
    trial_ends_at: Optional[datetime] = None


def _parse_dt(value) -> Optional[datetime]:
    """
    Accepts datetime, ISO string, or None.
    Returns naive datetime in UTC assumptions (consistent with your app's utc-naive pattern).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(value).strip()).replace(tzinfo=None)
    except Exception:
        return None


def get_trial_end(member_or_club) -> Optional[datetime]:
    """
    Trial end date source-of-truth:
      1) clubs.current_period_end (if set, use as "trial/pro period end")
      2) clubs.created_at + DEFAULT_TRIAL_DAYS (if created_at exists)
      3) None (unknown)
    """
    cpe = _parse_dt(getattr(member_or_club, "current_period_end", None))
    if cpe:
        return cpe

    created = _parse_dt(getattr(member_or_club, "created_at", None))
    if created:
        return created + timedelta(days=DEFAULT_TRIAL_DAYS)

    return None


def is_trial_expired(club) -> bool:
    end = get_trial_end(club)
    if not end:
        return False  # if we can't determine, don't brick them
    return datetime.utcnow() > end


def club_plan(club) -> str:
    plan = (getattr(club, "plan", None) or PLAN_FREE).strip().upper()
    return PLAN_PRO if plan == PLAN_PRO else PLAN_FREE


def gate_feature(club, feature: str) -> GateResult:
    """
    Central decision:
      - PRO always allowed
      - FREE allowed only if trial active
      - If trial expired -> blocked for PRO-only features AND (optionally) core features later
    """
    plan = club_plan(club)

    if plan == PLAN_PRO:
        return GateResult(True)

    # FREE trial mode
    end = get_trial_end(club)
    if end and datetime.utcnow() > end:
        return GateResult(False, reason="trial_expired", trial_ends_at=end)

    # During trial: allow everything (or selectively allow; we start generous)
    return GateResult(True, trial_ends_at=end)
