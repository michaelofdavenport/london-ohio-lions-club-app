# app/dependencies.py

from fastapi import Depends
from sqlalchemy.orm import Session

from .database import get_db
from .auth import get_current_member
from .models import Member


def db_session() -> Session:
    # Convenience alias if you want it later
    return next(get_db())


def current_member(
    member: Member = Depends(get_current_member),
) -> Member:
    """
    Router-friendly dependency wrapper.

    Your routers can import:
      from app.dependencies import get_current_member

    and we simply expose it here.
    """
    return member


# ✅ Keep the exact name your dashboard router expects:
get_current_member = current_member
