"""
ORM models for the `ballots` schema. Note AnonymousBallot has NO voter
reference of any kind — no voter_id, no token, no IP, no device fingerprint.
That is the entire point of this table (see ARCHITECTURE.md and
THREAT_MODEL.md).
"""
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Election(Base):
    __tablename__ = "elections"
    __table_args__ = (
        CheckConstraint("status IN ('draft','open','closed')", name="ck_election_status"),
        {"schema": "ballots"},
    )

    election_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="draft")
    opens_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closes_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_demo: Mapped[bool] = mapped_column(default=True)


class Constituency(Base):
    __tablename__ = "constituencies"
    __table_args__ = {"schema": "ballots"}

    constituency_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    election_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ballots.elections.election_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)


class FictionalCandidate(Base):
    __tablename__ = "fictional_candidates"
    __table_args__ = {"schema": "ballots"}

    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    election_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ballots.elections.election_id"), nullable=False)
    constituency_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ballots.constituencies.constituency_id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    symbol: Mapped[str] = mapped_column(String(60), nullable=False)
    manifesto_summary: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)


class AnonymousBallot(Base):
    """No voter_id. No token. No IP. No device fingerprint. On purpose."""

    __tablename__ = "anonymous_ballots"
    __table_args__ = (
        UniqueConstraint("election_id", "idempotency_key", name="uq_ballot_idempotency"),
        {"schema": "ballots"},
    )

    ballot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    election_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ballots.elections.election_id"), nullable=False)
    constituency_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ballots.constituencies.constituency_id"), nullable=False
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ballots.fictional_candidates.candidate_id"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False)
    reference_number: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    cast_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
