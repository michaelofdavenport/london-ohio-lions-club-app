# app/models.py
from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import (
    String,
    DateTime,
    Boolean,
    ForeignKey,
    Integer,
    Float,
    Date,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Club(Base):
    __tablename__ = "clubs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Slug is how we route public forms: ?club=london-ohio or /public/london-ohio/request
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ✅ Billing / Plans (Stripe)
    # Values: plan = FREE / PRO / ENTERPRISE
    # subscription_status examples: inactive / active / trialing / past_due / canceled
    plan: Mapped[str] = mapped_column(String(30), nullable=False, default="FREE")
    subscription_status: Mapped[str] = mapped_column(String(30), nullable=False, default="inactive")
    stripe_customer_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    members = relationship("Member", back_populates="club")
    requests = relationship("Request", back_populates="club")
    events = relationship("Event", back_populates="club")
    service_hours = relationship("ServiceHour", back_populates="club")


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # ✅ SaaS: members belong to a club
    club_id: Mapped[int | None] = mapped_column(ForeignKey("clubs.id"), nullable=True, index=True)

    # NOTE: email is globally unique right now.
    # For true multi-tenant you’d eventually want unique per club, not global.
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)

    member_since: Mapped[date | None] = mapped_column(Date, nullable=True)
    birthday: Mapped[date | None] = mapped_column(Date, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # ✅ Legacy admin flag (keep to avoid breaking anything already built)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    # ✅ HARD ROLE (Owner/Admin/Member) — this is what we will enforce going forward
    # Values: "OWNER" | "ADMIN" | "MEMBER"
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="MEMBER")

    # ✅ Platform-level super admin. Allows global visibility when needed.
    # Normal club admins remain is_admin=True but NOT is_super_admin.
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    club = relationship("Club", back_populates="members")

    reviewed_requests = relationship(
        "Request",
        back_populates="reviewed_by",
        foreign_keys="Request.reviewed_by_member_id",
    )
    assigned_requests = relationship(
        "Request",
        back_populates="assigned_to",
        foreign_keys="Request.assigned_to_member_id",
    )


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # ✅ SaaS: requests belong to a club
    club_id: Mapped[int | None] = mapped_column(ForeignKey("clubs.id"), nullable=True, index=True)

    category: Mapped[str] = mapped_column(String(40), nullable=False)  # EYE_CARE / COMMUNITY_ASSISTANCE
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING/APPROVED/DENIED/IN_PROGRESS/CLOSED
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)  # LOW/MED/HIGH (optional)

    requester_name: Mapped[str] = mapped_column(String(255), nullable=False)
    requester_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    requester_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requester_address: Mapped[str | None] = mapped_column(String(255), nullable=True)

    description: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Review fields
    reviewed_by_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Assignment + lifecycle fields
    assigned_to_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    club = relationship("Club", back_populates="requests")

    reviewed_by = relationship(
        "Member",
        back_populates="reviewed_requests",
        foreign_keys=[reviewed_by_member_id],
    )
    assigned_to = relationship(
        "Member",
        back_populates="assigned_requests",
        foreign_keys=[assigned_to_member_id],
    )

    notes = relationship("RequestNote", back_populates="request", cascade="all, delete-orphan")
    logs = relationship("RequestLog", back_populates="request", cascade="all, delete-orphan")


class RequestNote(Base):
    __tablename__ = "request_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), nullable=False, index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("members.id"), nullable=False)

    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    request = relationship("Request", back_populates="notes")
    author = relationship("Member")


class RequestLog(Base):
    __tablename__ = "request_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), nullable=False, index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("members.id"), nullable=False)

    action: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    request = relationship("Request", back_populates="logs")
    actor = relationship("Member")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # ✅ SaaS: events belong to a club
    club_id: Mapped[int | None] = mapped_column(ForeignKey("clubs.id"), nullable=True, index=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    is_public: Mapped[bool] = mapped_column(Boolean, default=True)

    created_by_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    club = relationship("Club", back_populates="events")


class ServiceHour(Base):
    __tablename__ = "service_hours"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # ✅ SaaS: service hours belong to a club (so summaries aren’t global)
    club_id: Mapped[int | None] = mapped_column(ForeignKey("clubs.id"), nullable=True, index=True)

    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), nullable=False)
    service_date: Mapped[date] = mapped_column(Date, default=date.today)
    hours: Mapped[float] = mapped_column(Float, nullable=False)
    activity: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    member = relationship("Member")
    club = relationship("Club", back_populates="service_hours")
