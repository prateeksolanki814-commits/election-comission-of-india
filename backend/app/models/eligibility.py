"""
ORM models for the `eligibility` schema. These models are used ONLY by
routers/services wired to the eligibility DB role. Deliberately no
relationship() to any ballot model — there is nothing to relate to, since
anonymous_ballots has no voter reference at all.
"""
import uuid

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserDemo(Base):
    __tablename__ = "users_demo"
    __table_args__ = {"schema": "eligibility"}

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SyntheticVoter(Base):
    __tablename__ = "synthetic_voters"
    __table_args__ = {"schema": "eligibility"}

    voter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    synthetic_voter_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    constituency_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    otp_secret_hash: Mapped[str] = mapped_column(String, nullable=False)
    language_pref: Mapped[str] = mapped_column(String(8), default="en")
    accessibility_prefs: Mapped[dict] = mapped_column(JSONB, default=dict)
    has_voted_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    is_eligible: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthAttempt(Base):
    __tablename__ = "auth_attempts"
    __table_args__ = {"schema": "eligibility"}

    attempt_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    voter_code_hash: Mapped[str] = mapped_column(String, nullable=False)
    ip_hash: Mapped[str] = mapped_column(String, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempted_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VotingCredential(Base):
    """The ONLY bridge between eligibility and ballots. No voter_id column
    — by design. See ARCHITECTURE.md section 3."""

    __tablename__ = "voting_credentials"
    __table_args__ = (
        CheckConstraint("status IN ('unused','used','expired')", name="ck_credential_status"),
        {"schema": "eligibility"},
    )

    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    election_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    constituency_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="unused")
    issued_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
