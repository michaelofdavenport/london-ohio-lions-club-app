# app/schemas.py

from datetime import datetime, date
from typing import Optional, Literal

from pydantic import BaseModel, EmailStr, Field

RequestCategory = Literal["EYE_CARE", "COMMUNITY_ASSISTANCE"]


# -----------------------------
# AUTH
# -----------------------------

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


# -----------------------------
# MEMBERS
# -----------------------------

class MemberOut(BaseModel):
    id: int
    email: EmailStr
    full_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None

    member_since: Optional[date] = None
    birthday: Optional[date] = None

    is_active: bool
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True


class MemberUpdateMe(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None

    member_since: Optional[date] = None
    birthday: Optional[date] = None


class MemberCreateIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None

    member_since: Optional[date] = None
    birthday: Optional[date] = None

    is_admin: bool = False


# ✅ Admin Tools PATCH payload (matches admin_tools.js)
class AdminMemberUpdateIn(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    member_since: Optional[date] = None
    birthday: Optional[date] = None
    is_admin: Optional[bool] = None


class AdminMemberActiveIn(BaseModel):
    is_active: bool


class AdminPasswordResetIn(BaseModel):
    password: str = Field(min_length=8)


# -----------------------------
# REQUESTS (PUBLIC + MEMBER)
# -----------------------------

class PublicRequestCreate(BaseModel):
    category: RequestCategory
    requester_name: str
    requester_phone: Optional[str] = None
    requester_email: Optional[EmailStr] = None
    requester_address: Optional[str] = None
    description: str


class RequestOut(BaseModel):
    id: int
    category: str
    status: str
    requester_name: str
    requester_phone: Optional[str] = None
    requester_email: Optional[str] = None
    requester_address: Optional[str] = None
    description: str
    created_at: datetime
    reviewed_by_member_id: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    decision_note: Optional[str] = None

    class Config:
        from_attributes = True


class RequestReviewIn(BaseModel):
    status: Literal["APPROVED", "DENIED"]
    decision_note: Optional[str] = None


# -----------------------------
# EVENTS
# -----------------------------

class EventCreateIn(BaseModel):
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    start_at: datetime
    end_at: Optional[datetime] = None
    is_public: bool = True


class EventUpdateIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    is_public: Optional[bool] = None


class EventOut(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    start_at: datetime
    end_at: Optional[datetime] = None
    is_public: bool
    created_by_member_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


# -----------------------------
# SERVICE HOURS
# -----------------------------

class ServiceHourCreateIn(BaseModel):
    service_date: date = Field(default_factory=date.today)
    hours: float = Field(gt=0)
    activity: str
    notes: Optional[str] = None


class ServiceHourUpdateIn(BaseModel):
    service_date: Optional[date] = None
    hours: Optional[float] = Field(default=None, gt=0)
    activity: Optional[str] = None
    notes: Optional[str] = None


class ServiceHourOut(BaseModel):
    id: int
    member_id: int
    service_date: date
    hours: float
    activity: str
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
