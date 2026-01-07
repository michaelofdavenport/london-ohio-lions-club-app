# app/auth.py

import os
import hashlib
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .database import get_db
from .models import Member

# -------------------------------------------------------------------
# Settings
# -------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_TO_SOMETHING_RANDOM_AND_LONG")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

# Force bcrypt module import early (helps avoid some backend detection weirdness)
# Even if passlib logs its "trapped" warning, this keeps behavior stable.
try:
    import bcrypt  # noqa: F401
except Exception:
    # If bcrypt isn't available, passlib will raise when hashing/verifying anyway.
    pass

# -------------------------------------------------------------------
# Password hashing
# -------------------------------------------------------------------
# ✅ Supports existing hashes AND fixes bcrypt 72-byte limit for new passwords.
# - New hashes will be bcrypt_sha256 (pre-hash with sha256 -> bcrypt)
# - Old hashes stored as bcrypt will still verify
pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"],
    deprecated="auto",
)

# Swagger will use this to send: Authorization: Bearer <token>
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/member/login")


def hash_password(password: str) -> str:
    """
    Hash a password for storage.
    Uses bcrypt_sha256 (safe for long passwords; avoids bcrypt 72-byte limit).
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a stored hash.
    Supports legacy bcrypt hashes and newer bcrypt_sha256 hashes.
    """
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str, expires_minutes: Optional[int] = None) -> str:
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes or ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if not sub:
            raise ValueError("Token missing subject")
        return sub
    except (JWTError, ValueError) as e:
        raise ValueError("Invalid token") from e


def get_current_member(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Member:
    """
    Validates Bearer token, loads Member by email (token subject),
    and returns the Member model.
    """
    try:
        email = decode_token(token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    member = db.query(Member).filter(Member.email == email).first()
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

    return member


def require_admin(member: Member = Depends(get_current_member)) -> Member:
    if not getattr(member, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return member
