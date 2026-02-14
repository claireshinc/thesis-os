"""
Thesis CRUD operations — persist compiled theses to Postgres.

Single-user mode (hardcoded user_id) until auth ships.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date as dt_date, datetime as dt_datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import Catalyst, Claim, KillCriterion, Thesis
from app.thesis import ThesisDraft

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_catalyst_date(date_str: str) -> dt_date:
    """Best-effort parse of catalyst date strings from LLM output."""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return dt_datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    # Quarter-style: "Q2 2025" → approximate to quarter-end
    date_str_upper = date_str.upper().strip()
    if date_str_upper.startswith("Q") and len(date_str_upper) >= 6:
        try:
            q = int(date_str_upper[1])
            year = int(date_str_upper.split()[-1])
            month = q * 3  # Q1→3, Q2→6, Q3→9, Q4→12
            return dt_date(year, month, 28)
        except (ValueError, IndexError):
            pass
    logger.info("Could not parse catalyst date '%s', using today", date_str)
    return dt_date.today()


# ---------------------------------------------------------------------------
# Save — ThesisDraft → DB rows
# ---------------------------------------------------------------------------


async def save_thesis(
    session: AsyncSession,
    draft: ThesisDraft,
    entry_price: float | None = None,
) -> Thesis:
    """
    Persist a compiled ThesisDraft to the database.

    Creates Thesis + Claim + KillCriterion + Catalyst rows.
    Claim/KC IDs are prefixed with a short thesis UUID to prevent PK collisions
    across multiple theses for the same ticker.
    """
    thesis = Thesis(
        user_id=DEFAULT_USER_ID,
        ticker=draft.ticker,
        direction=draft.direction,
        thesis_text=draft.thesis_text,
        sector_template=draft.sector,
        status="draft",
    )
    if entry_price is not None:
        thesis.entry_price = entry_price
        thesis.entry_date = dt_date.today()

    session.add(thesis)
    await session.flush()  # generates thesis.id

    prefix = str(thesis.id)[:8]

    # --- Claims ---
    for c in draft.claims:
        claim = Claim(
            id=f"{prefix}-{c.id}",
            thesis_id=thesis.id,
            statement=c.statement,
            kpi_id=c.kpi_id,
            current_value=c.current_value,
            qoq_delta=c.qoq_delta,
            yoy_delta=c.yoy_delta,
            status=getattr(c, "status", "supported"),
            last_updated=dt_datetime.utcnow(),
        )
        session.add(claim)

    # --- Kill Criteria ---
    for kc in draft.kill_criteria:
        criterion = KillCriterion(
            id=f"{prefix}-{kc.id}",
            thesis_id=thesis.id,
            description=kc.description,
            metric=kc.metric,
            operator=kc.operator,
            threshold=kc.threshold,
            duration=kc.duration,
            current_value=kc.current_value,
            status=kc.status,
            distance_pct=kc.distance_pct,
            watch_reason=kc.watch_reason,
            last_updated=dt_datetime.utcnow(),
        )
        session.add(criterion)

    # --- Catalysts ---
    for cat in draft.catalysts:
        catalyst = Catalyst(
            thesis_id=thesis.id,
            ticker=draft.ticker,
            event_date=_parse_catalyst_date(cat.expected_date),
            event=cat.event,
            claims_tested=cat.claims_tested,
            kill_criteria_tested=cat.kill_criteria_tested,
            occurred=False,
        )
        session.add(catalyst)

    await session.flush()
    return thesis


# ---------------------------------------------------------------------------
# Get — fetch by UUID with eager-loaded relationships
# ---------------------------------------------------------------------------


async def get_thesis(session: AsyncSession, thesis_id: uuid.UUID) -> Thesis | None:
    """Fetch a thesis with all relationships loaded."""
    stmt = (
        select(Thesis)
        .where(Thesis.id == thesis_id)
        .options(
            selectinload(Thesis.claims),
            selectinload(Thesis.kill_criteria),
            selectinload(Thesis.catalysts),
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# List — filtered listing
# ---------------------------------------------------------------------------


async def list_theses(
    session: AsyncSession,
    ticker: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Thesis]:
    """List theses with optional filters, ordered by created_at DESC."""
    stmt = select(Thesis).order_by(Thesis.created_at.desc())
    if ticker:
        stmt = stmt.where(Thesis.ticker == ticker.upper())
    if status:
        stmt = stmt.where(Thesis.status == status)
    stmt = stmt.offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Lock — draft → monitoring
# ---------------------------------------------------------------------------


async def lock_thesis(
    session: AsyncSession,
    thesis_id: uuid.UUID,
    entry_price: float | None = None,
) -> Thesis:
    """Transition a thesis from draft to monitoring."""
    thesis = await get_thesis(session, thesis_id)
    if thesis is None:
        raise ValueError(f"Thesis {thesis_id} not found")
    if thesis.status != "draft":
        raise ValueError(
            f"Cannot lock thesis with status '{thesis.status}' — must be 'draft'"
        )

    thesis.status = "monitoring"
    if entry_price is not None and thesis.entry_price is None:
        thesis.entry_price = entry_price
        thesis.entry_date = dt_date.today()

    return thesis


# ---------------------------------------------------------------------------
# Close — monitoring/draft → closed
# ---------------------------------------------------------------------------


async def close_thesis(
    session: AsyncSession,
    thesis_id: uuid.UUID,
    reason: str,
    close_price: float | None = None,
) -> Thesis:
    """Close a thesis with a reason."""
    thesis = await get_thesis(session, thesis_id)
    if thesis is None:
        raise ValueError(f"Thesis {thesis_id} not found")
    if thesis.status in ("closed", "killed"):
        raise ValueError(
            f"Thesis already '{thesis.status}' — cannot close again"
        )

    thesis.status = "closed"
    thesis.close_reason = reason
    thesis.close_date = dt_date.today()
    if close_price is not None:
        thesis.close_price = close_price

    return thesis
