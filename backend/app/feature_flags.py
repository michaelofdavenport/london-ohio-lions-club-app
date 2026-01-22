# app/feature_flags.py
from __future__ import annotations

"""
Central place to define access rules.

We support:
- Full access during a 7-day free trial (one-time per email, enforced via trial_redemptions table)
- After trial ends, user is hard-locked (except billing + login + public + static + health/version)
- PRO clubs have access regardless of trial state
"""

TRIAL_DAYS = 7

# These routes should ALWAYS be reachable (even if trial ended / not PRO).
# Keep this list small and obvious.
ALWAYS_ALLOWED_PREFIXES: tuple[str, ...] = (
    "/",
    "/health",
    "/version",
    "/static",
    "/public",
    "/billing",        # so they can pay
    "/member/login",   # so they can log in and see locked messaging
)

def is_always_allowed(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in ALWAYS_ALLOWED_PREFIXES)
