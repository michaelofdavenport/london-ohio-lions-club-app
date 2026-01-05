from datetime import datetime, date
from sqlalchemy import String, DateTime, Boolean, ForeignKey, Integer, Float, Date, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)

    member_since: Mapped[date | None] = mapped_column(Date, nullable=True)
    birthday: Mapped[date | None] = mapped_column(Date, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    reviewed_requests = relationship("Request", back_populates="reviewed_by", foreign_keys="Request.reviewed_by_member_id")
    assigned_requests = relationship("Request", back_populates="assigned_to", foreign_keys="Request.assigned_to_member_id")


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    category: Mapped[str] = mapped_column(String(40), nullable=False)  # EYE_CARE / COMMUNITY_ASSISTANCE
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING/APPROVED/DENIED/IN_PROGRESS/CLOSED
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)  # LOW/MED/HIGH (optional)

    requester_name: Mapped[str] = mapped_column(String(255), nullable=False)
    requester_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    requester_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requester_address: Mapped[str | None] = mapped_column(String(255), nullable=True)

    description: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Review fields (already in your schema)
    reviewed_by_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ✅ NEW: assignment + lifecycle fields
    assigned_to_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    reviewed_by = relationship("Member", back_populates="reviewed_requests", foreign_keys=[reviewed_by_member_id])
    assigned_to = relationship("Member", back_populates="assigned_requests", foreign_keys=[assigned_to_member_id])

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

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    is_public: Mapped[bool] = mapped_column(Boolean, default=True)

    created_by_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ServiceHour(Base):
    __tablename__ = "service_hours"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), nullable=False)
    service_date: Mapped[date] = mapped_column(Date, default=date.today)
    hours: Mapped[float] = mapped_column(Float, nullable=False)
    activity: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    member = relationship("Member")
