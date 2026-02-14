"""
Database engine, session factory, and all SQLAlchemy models.

Tables: theses, claims, kill_criteria, evidence, change_events, catalysts
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Theses — the core object a PM creates
# ---------------------------------------------------------------------------
class Thesis(Base):
    __tablename__ = "theses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # long / short
    thesis_text: Mapped[str] = mapped_column(Text, nullable=False)
    sector_template: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft"
    )  # draft, monitoring, killed, closed

    entry_price: Mapped[float | None] = mapped_column(Numeric(12, 4))
    entry_date: Mapped[date | None] = mapped_column(Date)
    close_price: Mapped[float | None] = mapped_column(Numeric(12, 4))
    close_date: Mapped[date | None] = mapped_column(Date)
    close_reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    claims: Mapped[list[Claim]] = relationship(back_populates="thesis", cascade="all, delete-orphan")
    kill_criteria: Mapped[list[KillCriterion]] = relationship(
        back_populates="thesis", cascade="all, delete-orphan"
    )
    catalysts: Mapped[list[Catalyst]] = relationship(
        back_populates="thesis", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Claims — falsifiable statements within a thesis
# ---------------------------------------------------------------------------
class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # e.g. ASML-C1
    thesis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("theses.id"), nullable=False
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    kpi_id: Mapped[str] = mapped_column(String(50), nullable=False)
    current_value: Mapped[float | None] = mapped_column(Numeric(16, 4))
    qoq_delta: Mapped[float | None] = mapped_column(Numeric(10, 4))
    yoy_delta: Mapped[float | None] = mapped_column(Numeric(10, 4))
    status: Mapped[str] = mapped_column(
        String(20), default="supported"
    )  # supported, mixed, challenged
    last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    thesis: Mapped[Thesis] = relationship(back_populates="claims")
    evidence: Mapped[list[Evidence]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Kill criteria — quantitative trip-wires
# ---------------------------------------------------------------------------
class KillCriterion(Base):
    __tablename__ = "kill_criteria"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    thesis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("theses.id"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    metric: Mapped[str] = mapped_column(String(50), nullable=False)
    operator: Mapped[str] = mapped_column(String(10), nullable=False)
    threshold: Mapped[float] = mapped_column(Numeric(16, 4), nullable=False)
    duration: Mapped[str | None] = mapped_column(String(20))  # 2Q, 1Y, etc.

    current_value: Mapped[float | None] = mapped_column(Numeric(16, 4))
    current_source: Mapped[dict | None] = mapped_column(JSONB)  # Citation as JSON
    status: Mapped[str] = mapped_column(String(10), default="ok")  # ok, watch, breach
    distance_pct: Mapped[float | None] = mapped_column(Numeric(10, 4))
    watch_reason: Mapped[str | None] = mapped_column(Text)
    last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    thesis: Mapped[Thesis] = relationship(back_populates="kill_criteria")


# ---------------------------------------------------------------------------
# Evidence — citations linked to claims
# ---------------------------------------------------------------------------
class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("claims.id"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(15), nullable=False)  # supporting / disconfirming
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(15), nullable=False)  # fact / interpretation

    # Citation fields — sufficient to reconstruct a full Citation object
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    filer: Mapped[str | None] = mapped_column(Text)
    filing_date: Mapped[date | None] = mapped_column(Date)
    section: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    accession_number: Mapped[str | None] = mapped_column(String(30))
    url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    claim: Mapped[Claim] = relationship(back_populates="evidence")


# ---------------------------------------------------------------------------
# Change events — the "What Changed" feed
# ---------------------------------------------------------------------------
class ChangeEvent(Base):
    __tablename__ = "change_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)  # info, watch, breach

    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    what_changed: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[dict] = mapped_column(JSONB, nullable=False)  # Citation as JSON

    interpretation: Mapped[str | None] = mapped_column(Text)
    interpretation_is_fact: Mapped[bool] = mapped_column(Boolean, default=False)

    claims_impacted: Mapped[list | None] = mapped_column(JSONB)
    claim_impact: Mapped[str | None] = mapped_column(String(15))
    kill_criteria_impacted: Mapped[list | None] = mapped_column(JSONB)
    kill_status_change: Mapped[str | None] = mapped_column(String(30))

    raw_data: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        Index("idx_change_events_ticker", "ticker", timestamp.desc()),
        Index("idx_change_events_severity", "severity", timestamp.desc()),
    )


# ---------------------------------------------------------------------------
# Catalysts — dated events that test claims or kill criteria
# ---------------------------------------------------------------------------
class Catalyst(Base):
    __tablename__ = "catalysts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thesis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("theses.id"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event: Mapped[str] = mapped_column(Text, nullable=False)
    claims_tested: Mapped[list | None] = mapped_column(JSONB)
    kill_criteria_tested: Mapped[list | None] = mapped_column(JSONB)
    occurred: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome_notes: Mapped[str | None] = mapped_column(Text)

    thesis: Mapped[Thesis] = relationship(back_populates="catalysts")


# ---------------------------------------------------------------------------
# Lifecycle helpers
# ---------------------------------------------------------------------------
async def init_db() -> None:
    """Create all tables. Use Alembic for migrations in production."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency — yields an async session."""
    async with async_session() as session:
        yield session
