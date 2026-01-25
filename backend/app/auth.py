# backend/app/auth.py
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Member, Club

# -------------------------------------------------------------------
# Settings
# -------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_TO_SOMETHING_RANDOM_AND_LONG")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

# Force bcrypt import early (stability)
try:
    import bcrypt  # noqa: F401
except Exception:
    pass

# -------------------------------------------------------------------
# Password hashing
# -------------------------------------------------------------------
pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"],
    deprecated="auto",
)

# Swagger will use this to send: Authorization: Bearer <token>
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/member/login")

# -------------------------------------------------------------------
# Roles
# -------------------------------------------------------------------
ROLE_OWNER = "OWNER"
ROLE_ADMIN = "ADMIN"
ROLE_MEMBER = "MEMBER"
VALID_ROLES = {ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER}


def normalize_role(value: Optional[str]) -> str:
    r = (value or "").strip().upper()
    return r if r in VALID_ROLES else ROLE_MEMBER


def is_owner(member: Member) -> bool:
    return normalize_role(getattr(member, "role", None)) == ROLE_OWNER


def is_admin_role(member: Member) -> bool:
    """
    Hard-role admin check:
      OWNER or ADMIN => admin-capable
    """
    return normalize_role(getattr(member, "role", None)) in (ROLE_OWNER, ROLE_ADMIN)


# -------------------------------------------------------------------
# Password helpers
# -------------------------------------------------------------------
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# -------------------------------------------------------------------
# SaaS helpers
# -------------------------------------------------------------------
DEFAULT_CLUB_SLUG = os.getenv("DEFAULT_CLUB_SLUG", "london-ohio")


def resolve_club(db: Session, club_slug: Optional[str]) -> Club:
    """
    Resolve club_slug -> Club row. If missing, use DEFAULT_CLUB_SLUG.
    """
    slug = (club_slug or "").strip() or DEFAULT_CLUB_SLUG
    club = db.scalar(select(Club).where(Club.slug == slug, Club.is_active == True))  # noqa: E712
    if not club:
        raise HTTPException(status_code=400, detail="Invalid club")
    return club


def extract_club_slug_from_oauth(form_data) -> Optional[str]:
    """
    OAuth2PasswordRequestForm does not have a dedicated 'club' field.
    It DOES include 'scopes', sent from the client as:
      scope=club:london-ohio
    We support:
      - scope=club:london-ohio
      - scope=london-ohio   (simple)
    """
    scopes = getattr(form_data, "scopes", None) or []
    if not scopes:
        return None

    for s in scopes:
        s = (s or "").strip()
        if not s:
            continue
        if s.startswith("club:"):
            return s.split("club:", 1)[1].strip() or None
        # allow bare slug as a scope
        return s

    return None


# -------------------------------------------------------------------
# JWT create/verify
# -------------------------------------------------------------------
def create_access_token(
    *,
    member_id: int,
    club_id: int,
    is_admin: bool,
    subject: str,
    is_super_admin: bool = False,
    role: Optional[str] = None,
    expires_minutes: Optional[int] = None,
) -> str:
    """
    Token claims:
      sub: email (debug/compat)
      mid: member id
      cid: club id
      adm: admin flag (legacy / compatibility)
      sad: super-admin flag
      rol: role (OWNER/ADMIN/MEMBER)
      exp: expiry datetime
    """
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes or ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": subject,                 # keep for compatibility/debug (email)
        "mid": int(member_id),          # member id
        "cid": int(club_id),            # club id
        "adm": bool(is_admin),          # legacy admin flag (do not remove)
        "sad": bool(is_super_admin),    # super-admin flag
        "rol": normalize_role(role),    # hard role
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if not payload.get("mid") or not payload.get("cid"):
            raise ValueError("Token missing required claims")
        return payload
    except (JWTError, ValueError) as e:
        raise ValueError("Invalid token") from e


# -------------------------------------------------------------------
# Internal helpers (used by BOTH dependency + middleware)
# -------------------------------------------------------------------
def _load_member_from_claims(db: Session, member_id: int, club_id: int) -> Member:
    member = (
        db.query(Member)
        .filter(Member.id == member_id, Member.club_id == club_id)
        .first()
    )

    if not member:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not member.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive member",
        )

    # Safety: normalize role if missing/garbage (doesn't write DB, just prevents surprises)
    try:
        member.role = normalize_role(getattr(member, "role", None))
    except Exception:
        pass

    return member


def _auth_401() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


# -------------------------------------------------------------------
# Dependencies
# -------------------------------------------------------------------
def get_current_member(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Member:
    """
    Validates Bearer token and loads the Member by (member_id, club_id).
    This is the core SaaS isolation rule.
    """
    try:
        payload = decode_token(token)
        member_id = int(payload["mid"])
        club_id = int(payload["cid"])
    except Exception:
        raise _auth_401()

    return _load_member_from_claims(db, member_id, club_id)


def get_current_member_from_request(request: Request, db: Session) -> Member:
    """
    Middleware-safe auth:
      - Reads Authorization header
      - Validates Bearer token
      - Loads member by (mid, cid)
    """
    auth_header = (request.headers.get("Authorization") or "").strip()
    if not auth_header:
        raise _auth_401()

    # Expect: "Bearer <token>"
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise _auth_401()

    token = parts[1].strip()
    if not token:
        raise _auth_401()

    try:
        payload = decode_token(token)
        member_id = int(payload["mid"])
        club_id = int(payload["cid"])
    except Exception:
        raise _auth_401()

    return _load_member_from_claims(db, member_id, club_id)


def require_admin(member: Member = Depends(get_current_member)) -> Member:
    """
    Backward compatible:
      - If role exists: OWNER or ADMIN passes.
      - Otherwise: fall back to old is_admin flag.
    """
    role_val = getattr(member, "role", None)
    if role_val is not None:
        if not is_admin_role(member):
            raise HTTPException(status_code=403, detail="Admin privileges required")
        return member

    # legacy fallback
    if not getattr(member, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return member


def require_owner(member: Member = Depends(get_current_member)) -> Member:
    """
    Hard OWNER gate.
    """
    if not is_owner(member):
        raise HTTPException(status_code=403, detail="Owner privileges required")
    return member


def require_super_admin(member: Member = Depends(get_current_member)) -> Member:
    """
    Super admin is optional, used for cross-club administration.
    """
    if not getattr(member, "is_super_admin", False):
        raise HTTPException(status_code=403, detail="Super admin privileges required")
    return member


# -------------------------------------------------------------------
# ADDITIONS (safe): app URL + email config + temp password
# -------------------------------------------------------------------
def app_base_url() -> str:
    """
    Used in invite emails and links.
    In production set APP_BASE_URL, e.g. https://yourdomain.com
    """
    base = (os.getenv("APP_BASE_URL") or "").strip().rstrip("/")
    return base or "http://127.0.0.1:8000"


def email_configured() -> bool:
    """
    True if SMTP env vars are present (emailer can attempt to send).
    """
    host = (os.getenv("SMTP_HOST") or "").strip()
    user = (os.getenv("SMTP_USER") or "").strip()
    pw = (os.getenv("SMTP_PASS") or "").strip()
    return bool(host and user and pw)


def make_temp_password(length: int = 14) -> str:
    """
    Generates a temporary password string.
    """
    return secrets.token_urlsafe(length)[:length]
