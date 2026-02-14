"""
Change detection — on-demand "what changed" feed for a ticker.

Checks three sources:
  1. New SEC filings since a given date
  2. New insider transactions since a given date
  3. KPI moves approaching kill criteria (if user has an active thesis)

Returns Pydantic response objects — does NOT persist to DB.
The ChangeEvent table exists for future scheduled persistence.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.data import get_company_filings, get_insider_details

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ChangeEventResponse(BaseModel):
    """One detected change — mirrors ChangeEvent DB model structure."""
    id: str
    ticker: str
    timestamp: str
    severity: str  # "info", "watch", "breach"
    event_type: str  # "new_filing", "insider_transaction", "kpi_threshold"
    what_changed: str
    source: dict[str, Any]
    claims_impacted: list[str] | None = None
    claim_impact: str | None = None
    kill_criteria_impacted: list[str] | None = None
    kill_status_change: str | None = None
    raw_data: dict[str, Any] | None = None


class ChangeFeedResponse(BaseModel):
    """Full change feed response."""
    ticker: str
    since: str
    events: list[ChangeEventResponse]
    event_count: int
    checked_at: str


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def detect_changes(
    ticker: str,
    since_date: date,
    session: AsyncSession | None = None,
) -> ChangeFeedResponse:
    """
    On-demand change detection for a ticker.

    Checks for new SEC filings, insider transactions, and KPI threshold
    proximity since the given date.
    """
    ticker = ticker.upper()
    since_str = since_date.isoformat()
    events: list[ChangeEventResponse] = []

    # 1. New filings
    filing_events = await _check_new_filings(ticker, since_str)
    events.extend(filing_events)

    # 2. Insider transactions
    insider_events = await _check_insider_transactions(ticker, since_str)
    events.extend(insider_events)

    # 3. KPI threshold proximity (only if DB session available)
    if session is not None:
        kpi_events = await _check_kpi_thresholds(ticker, session)
        events.extend(kpi_events)

    # Sort by timestamp descending (most recent first)
    events.sort(key=lambda e: e.timestamp, reverse=True)

    return ChangeFeedResponse(
        ticker=ticker,
        since=since_str,
        events=events,
        event_count=len(events),
        checked_at=datetime.utcnow().isoformat() + "Z",
    )


# ---------------------------------------------------------------------------
# Check 1: New SEC filings
# ---------------------------------------------------------------------------


async def _check_new_filings(
    ticker: str,
    since_str: str,
) -> list[ChangeEventResponse]:
    """Find filings with filing_date >= since_str."""
    events: list[ChangeEventResponse] = []

    try:
        result = await get_company_filings(ticker, form_types=None, limit=40)

        for filing in result.data:
            filing_date = filing.get("filing_date", "")
            if filing_date < since_str:
                continue

            form_type = filing.get("form_type", "unknown")

            # Skip filing types that are noise (e.g. EFFECT, SC 13G/A amendments)
            # Focus on substantive filings
            severity = "info"
            if form_type in ("10-K", "10-K/A", "10-Q", "10-Q/A"):
                severity = "watch"
            elif form_type in ("8-K", "8-K/A"):
                severity = "watch"

            events.append(ChangeEventResponse(
                id=str(uuid.uuid4()),
                ticker=ticker,
                timestamp=f"{filing_date}T00:00:00Z",
                severity=severity,
                event_type="new_filing",
                what_changed=f"New {form_type} filed on {filing_date}",
                source={
                    "source_type": form_type,
                    "accession_number": filing.get("accession_number"),
                    "url": filing.get("url", ""),
                    "filing_date": filing_date,
                },
                raw_data=filing,
            ))
    except Exception as exc:
        logger.warning("Failed to check filings for %s: %s", ticker, exc)

    return events


# ---------------------------------------------------------------------------
# Check 2: Insider transactions
# ---------------------------------------------------------------------------

_TXN_CODE_MAP = {
    "P": "purchased",
    "S": "sold",
    "A": "was awarded",
    "M": "exercised options for",
    "G": "gifted",
    "F": "paid tax via",
    "D": "disposed of",
}


async def _check_insider_transactions(
    ticker: str,
    since_str: str,
) -> list[ChangeEventResponse]:
    """Find insider transactions with transaction_date >= since_str."""
    events: list[ChangeEventResponse] = []

    try:
        result = await get_insider_details(ticker, limit=20)

        for txn in result.data:
            txn_date = txn.get("transaction_date", "")
            if not txn_date or txn_date < since_str:
                continue

            code = txn.get("transaction_code", "")
            owner = txn.get("owner_name", "unknown")
            title = txn.get("owner_title", "")
            shares = txn.get("shares")
            value = txn.get("value")
            is_10b5_1 = txn.get("is_10b5_1", False)

            action = _TXN_CODE_MAP.get(code, f"transacted ({code})")
            shares_str = f"{shares:,.0f} shares" if shares else "shares"
            value_str = f" (${value:,.0f})" if value else ""
            plan_str = " [10b5-1 plan]" if is_10b5_1 else ""

            # Severity: discretionary purchases are notable
            severity = "info"
            if code == "P" and not is_10b5_1:
                severity = "watch"
            elif code == "S" and not is_10b5_1 and value and value > 500_000:
                severity = "watch"

            events.append(ChangeEventResponse(
                id=str(uuid.uuid4()),
                ticker=ticker,
                timestamp=f"{txn_date}T00:00:00Z",
                severity=severity,
                event_type="insider_transaction",
                what_changed=(
                    f"{owner} ({title}) {action} {shares_str}{value_str}{plan_str}"
                ),
                source={
                    "source_type": "form4",
                    "filer": owner,
                    "accession_number": txn.get("accession_number"),
                    "filing_date": txn.get("filing_date"),
                },
                raw_data=txn,
            ))
    except Exception as exc:
        logger.warning("Failed to check insider transactions for %s: %s", ticker, exc)

    return events


# ---------------------------------------------------------------------------
# Check 3: KPI threshold proximity
# ---------------------------------------------------------------------------


async def _check_kpi_thresholds(
    ticker: str,
    session: AsyncSession,
) -> list[ChangeEventResponse]:
    """
    If user has an active thesis (status='monitoring') for this ticker,
    run QuantEngine to get fresh KPIs and compare to kill criteria thresholds.
    """
    from app import crud
    from app.brief import detect_sector
    from app.quant import QuantEngine
    from app.thesis import _evaluate_kill_criterion

    events: list[ChangeEventResponse] = []

    # Find active theses for this ticker
    active = await crud.list_theses(session, ticker=ticker, status="monitoring", limit=5)
    if not active:
        return events

    # Run quant engine for fresh KPIs
    try:
        _, template, _ = await detect_sector(ticker)
        quant = QuantEngine()
        quant_output = await quant.analyze(ticker, template)
    except Exception as exc:
        logger.warning("Quant engine failed for KPI check on %s: %s", ticker, exc)
        return events

    # For each active thesis, check kill criteria against fresh KPIs
    for thesis_summary in active:
        thesis = await crud.get_thesis(session, thesis_summary.id)
        if thesis is None:
            continue

        for kc in thesis.kill_criteria:
            kpi_data = quant_output.sector_kpis.get(kc.metric)
            if kpi_data is None or kpi_data.value is None:
                continue

            fresh_value = kpi_data.value
            status, distance = _evaluate_kill_criterion(
                fresh_value, float(kc.threshold), kc.operator,
            )

            if status in ("watch", "breach"):
                old_status = kc.status or "ok"
                status_change = f"{old_status} -> {status}" if old_status != status else None

                events.append(ChangeEventResponse(
                    id=str(uuid.uuid4()),
                    ticker=ticker,
                    timestamp=datetime.utcnow().isoformat() + "Z",
                    severity=status,
                    event_type="kpi_threshold",
                    what_changed=(
                        f"Kill criterion '{kc.description}': "
                        f"{kc.metric} is {fresh_value:.2f} "
                        f"(threshold: {kc.operator} {float(kc.threshold):.2f}, "
                        f"distance: {distance:.1f}%)"
                    ),
                    source={
                        "source_type": "quant_engine",
                        "kpi_id": kc.metric,
                        "period": kpi_data.period,
                    },
                    kill_criteria_impacted=[kc.id],
                    kill_status_change=status_change,
                    raw_data={
                        "kill_criterion_id": kc.id,
                        "metric": kc.metric,
                        "threshold": float(kc.threshold),
                        "operator": kc.operator,
                        "current_value": fresh_value,
                        "prior_status": old_status,
                        "new_status": status,
                        "distance_pct": distance,
                    },
                ))

    return events
