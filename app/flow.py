"""
Flow engine — 13F holder map + insider transaction analysis.

Provides:
  1. Insider transaction filter: 10b5-1 vs discretionary, size relative to
     holdings, contextual notes, notable-transaction flagging.
  2. Holder map builder: institutional holder context with explicit data-lag
     labeling. (v1: metadata-only; full 13F position parsing is a later phase.)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.data import (
    DataResult,
    SourceMeta,
    get_13f_holdings,
    get_insider_details,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class InsiderTransaction:
    owner_name: str
    owner_title: str
    transaction_date: str
    transaction_type: str  # "purchase", "sale", "option_exercise", "award", "other"
    shares: float | None
    price_per_share: float | None
    value: float | None
    shares_owned_after: float | None
    is_10b5_1: bool
    is_discretionary: bool
    pct_of_holdings: float | None
    is_notable: bool
    context_note: str
    source: SourceMeta


@dataclass
class HolderEntry:
    filer_name: str
    form_type: str
    filing_date: str
    accession_number: str | None
    # v1: metadata only — shares/value require 13F info table parsing (TODO)
    shares: int | None = None
    value: float | None = None
    fund_type: str = "unknown"  # "hedge_fund", "long_only", "index", "unknown"


@dataclass
class HolderMap:
    """Institutional holder context — NOT an alpha signal."""

    top_holders: list[HolderEntry]
    holder_count: int
    insider_activity: list[InsiderTransaction]
    insider_summary: str
    data_freshness: dict[str, str]
    holder_data_note: str = ""  # non-empty when data is stale or incomplete


@dataclass
class FlowOutput:
    ticker: str
    holder_map: HolderMap
    computed_at: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Transaction code → human-readable type
# ---------------------------------------------------------------------------

_TXN_TYPE_MAP: dict[str, str] = {
    "P": "purchase",
    "S": "sale",
    "A": "award",
    "M": "option_exercise",
    "G": "gift",
    "F": "tax_withholding",
    "C": "conversion",
    "D": "disposition_to_issuer",
    "J": "other",
}


def _txn_type(code: str) -> str:
    return _TXN_TYPE_MAP.get(code, "other")


# ---------------------------------------------------------------------------
# Fund classification heuristic
# ---------------------------------------------------------------------------

_HF_KEYWORDS = frozenset({
    "capital", "partners", "advisors", "management", "fund", "associates",
    "lp", "llc", "investments",
})
_INDEX_KEYWORDS = frozenset({
    "vanguard", "blackrock", "state street", "ishares", "fidelity",
    "schwab", "spdr", "index",
})
_LONG_ONLY_KEYWORDS = frozenset({
    "wellington", "t. rowe", "capital group", "dodge & cox",
    "mfs", "putnam", "american funds",
})


def _classify_fund(name: str) -> str:
    """
    Simple heuristic fund classification from name alone.
    Good enough for context labeling, not for quantitative analysis.
    """
    lower = name.lower()
    for kw in _INDEX_KEYWORDS:
        if kw in lower:
            return "index"
    for kw in _LONG_ONLY_KEYWORDS:
        if kw in lower:
            return "long_only"
    # Most remaining 13F filers with capital/partners in name are HF-ish
    words = set(lower.split())
    if words & _HF_KEYWORDS and len(lower) < 60:
        return "hedge_fund"
    return "unknown"


# ---------------------------------------------------------------------------
# FlowEngine
# ---------------------------------------------------------------------------

class FlowEngine:
    """
    Holder mapping and insider transaction analysis.

    Usage:
        engine = FlowEngine()
        output = await engine.analyze("AAPL")
    """

    async def analyze(self, ticker: str) -> FlowOutput:
        """Run full flow analysis: insider transactions + holder map."""

        # Fetch insider details (parsed Form 4 XML)
        insider_result = await get_insider_details(ticker, limit=15)
        raw_txns = insider_result.data

        # Filter and contextualize insider transactions
        insider_activity = self._filter_insider_transactions(raw_txns, ticker)

        # Build holder map (v1: metadata only, freshness-filtered)
        holder_map_entries, holder_data_note = await self._build_holder_map(ticker)

        # Summarize insider activity
        insider_summary = self._summarize_insider_activity(insider_activity)

        # Determine data freshness
        freshness: dict[str, str] = {}
        if insider_activity:
            latest_date = max(t.transaction_date for t in insider_activity)
            freshness["insider_latest"] = latest_date
        freshness["insider_note"] = (
            "Form 4 filings are due within 2 business days of the transaction."
        )
        if holder_map_entries:
            latest_13f = max(h.filing_date for h in holder_map_entries)
            freshness["13f_latest"] = latest_13f
        freshness["13f_note"] = (
            "13F filings report quarter-end holdings with a 45-day filing deadline. "
            "Data shown may be up to 4.5 months stale."
        )
        if holder_data_note:
            freshness["13f_warning"] = holder_data_note

        return FlowOutput(
            ticker=ticker.upper(),
            holder_map=HolderMap(
                top_holders=holder_map_entries,
                holder_count=len(holder_map_entries),
                insider_activity=insider_activity,
                insider_summary=insider_summary,
                data_freshness=freshness,
                holder_data_note=holder_data_note,
            ),
        )

    # -------------------------------------------------------------------
    # Insider transaction filtering
    # -------------------------------------------------------------------

    def _filter_insider_transactions(
        self, raw_txns: list[dict], ticker: str,
    ) -> list[InsiderTransaction]:
        """
        Transform raw Form 4 data into contextualized InsiderTransactions.

        Key logic:
        - 10b5-1 plan transactions are labeled as non-discretionary
        - Pct of holdings is computed from shares / shares_owned_after
        - Only discretionary purchases are flagged as notable
        - Contextual notes explain each transaction's significance
        """
        results: list[InsiderTransaction] = []

        for txn in raw_txns:
            code = txn.get("transaction_code", "")
            txn_type = _txn_type(code)

            # Skip non-meaningful codes (gifts, tax withholding, etc.)
            if txn_type in ("gift", "tax_withholding", "other", "conversion"):
                continue

            is_10b5_1 = txn.get("is_10b5_1", False)
            is_discretionary = not is_10b5_1

            shares = txn.get("shares")
            shares_after = txn.get("shares_owned_after")
            price = txn.get("price_per_share")
            value = txn.get("value")

            # Compute size relative to holdings
            pct_of_holdings: float | None = None
            if shares and shares_after and shares_after > 0:
                # For sales: shares sold / total before sale
                # For purchases: shares bought / total after purchase
                if code == "S":
                    total_before = shares_after + shares
                    pct_of_holdings = shares / total_before if total_before > 0 else None
                else:
                    pct_of_holdings = shares / shares_after if shares_after > 0 else None

            # Determine if notable + build context note
            is_notable = False
            context_note = ""

            if is_10b5_1:
                pct_str = f"{pct_of_holdings:.1%} of holdings" if pct_of_holdings else "unknown % of holdings"
                context_note = (
                    f"10b5-1 plan transaction ({pct_str}). "
                    f"Routine unless plan was recently adopted or modified."
                )
            elif code == "S" and pct_of_holdings is not None and pct_of_holdings < 0.05:
                context_note = (
                    f"Discretionary sale but small ({pct_of_holdings:.1%} of holdings). "
                    f"Likely tax or liquidity-driven."
                )
            elif code == "S" and pct_of_holdings is not None and pct_of_holdings >= 0.05:
                context_note = (
                    f"Discretionary sale of {pct_of_holdings:.1%} of holdings "
                    f"by {txn.get('owner_title', 'insider')}. "
                    f"Significant size warrants attention."
                )
                is_notable = True
            elif code == "P" and is_discretionary:
                val_str = f"${value:,.0f}" if value else "unknown value"
                pct_str = f" ({pct_of_holdings:.1%} increase)" if pct_of_holdings else ""
                context_note = (
                    f"Discretionary purchase by {txn.get('owner_title', 'insider')} "
                    f"for {val_str}{pct_str}. "
                    f"Open-market buys by insiders are the most informative signal."
                )
                is_notable = True
            elif txn_type == "option_exercise":
                context_note = (
                    f"Option exercise by {txn.get('owner_title', 'insider')}. "
                    f"Routine compensation event — only notable if shares were retained."
                )
            elif txn_type == "award":
                context_note = (
                    f"Equity award to {txn.get('owner_title', 'insider')}. "
                    f"Compensation grant — not a market signal."
                )

            cik = txn.get("cik", "")
            cik_num = cik.lstrip("0") or "0"
            accession = txn.get("accession_number", "")
            acc_no_dashes = accession.replace("-", "")

            results.append(InsiderTransaction(
                owner_name=txn.get("owner_name", ""),
                owner_title=txn.get("owner_title", ""),
                transaction_date=txn.get("transaction_date", ""),
                transaction_type=txn_type,
                shares=shares,
                price_per_share=price,
                value=value,
                shares_owned_after=shares_after,
                is_10b5_1=is_10b5_1,
                is_discretionary=is_discretionary,
                pct_of_holdings=pct_of_holdings,
                is_notable=is_notable,
                context_note=context_note,
                source=SourceMeta(
                    source_type="form4",
                    filer=txn.get("owner_name", ""),
                    filing_date=(
                        date.fromisoformat(txn["filing_date"])
                        if txn.get("filing_date") else None
                    ),
                    accession_number=accession,
                    section="Statement of Changes in Beneficial Ownership",
                    url=(
                        f"https://www.sec.gov/Archives/edgar/data/{cik_num}/"
                        f"{acc_no_dashes}/{accession}-index.htm"
                    ) if accession else "",
                ),
            ))

        # Sort by date descending
        results.sort(key=lambda t: t.transaction_date, reverse=True)
        return results

    # -------------------------------------------------------------------
    # Holder map builder (v1: metadata + classification)
    # -------------------------------------------------------------------

    async def _build_holder_map(
        self, ticker: str,
    ) -> tuple[list[HolderEntry], str]:
        """
        Build holder map from 13F filing metadata.

        Filters to filings from the last 2 quarters (~6 months).
        Returns (entries, data_note) where data_note is non-empty when
        data is stale or insufficient.
        """
        try:
            holdings_result = await get_13f_holdings(ticker, limit=20)
        except Exception as exc:
            logger.warning("Failed to fetch 13F data for %s: %s", ticker, exc)
            return [], "No 13F data available."

        # Freshness cutoff: ~6 months ago (2 quarters)
        from datetime import timedelta
        cutoff = (date.today() - timedelta(days=180)).isoformat()

        entries: list[HolderEntry] = []
        seen_filers: set[str] = set()

        for h in holdings_result.data:
            name = h.get("filer_name", "")
            if not name or name in seen_filers:
                continue

            filing_date = h.get("filing_date", "")
            if filing_date and filing_date < cutoff:
                continue  # Skip stale filings (older than 2 quarters)

            seen_filers.add(name)
            entries.append(HolderEntry(
                filer_name=name,
                form_type=h.get("form_type", "13F-HR"),
                filing_date=filing_date,
                accession_number=h.get("accession_number"),
                fund_type=_classify_fund(name),
            ))

        data_note = ""
        if len(entries) < 3:
            data_note = (
                "Insufficient recent 13F data — holder map incomplete. "
                f"Only {len(entries)} holder(s) filed within the last 2 quarters."
            )

        return entries, data_note

    # -------------------------------------------------------------------
    # Insider activity summary
    # -------------------------------------------------------------------

    def _summarize_insider_activity(
        self, transactions: list[InsiderTransaction],
    ) -> str:
        """One-paragraph summary of recent insider activity."""
        if not transactions:
            return "No insider transactions found in recent Form 4 filings."

        purchases = [t for t in transactions if t.transaction_type == "purchase"]
        sales = [t for t in transactions if t.transaction_type == "sale"]
        exercises = [t for t in transactions if t.transaction_type == "option_exercise"]
        notable = [t for t in transactions if t.is_notable]
        discretionary_sales = [t for t in sales if t.is_discretionary]
        plan_sales = [t for t in sales if t.is_10b5_1]

        parts: list[str] = []
        parts.append(
            f"{len(transactions)} insider transactions in recent filings: "
            f"{len(purchases)} purchases, {len(sales)} sales, "
            f"{len(exercises)} option exercises."
        )

        if plan_sales:
            parts.append(
                f"{len(plan_sales)} of {len(sales)} sales were under 10b5-1 plans (routine)."
            )

        if notable:
            names = ", ".join(set(t.owner_name for t in notable[:3]))
            parts.append(f"Notable activity from: {names}.")

        if purchases and not sales:
            parts.append("Net buying by insiders — typically a positive signal.")
        elif discretionary_sales and not purchases:
            total_val = sum(t.value or 0 for t in discretionary_sales)
            if total_val > 0:
                parts.append(
                    f"Net discretionary selling totaling ${total_val:,.0f}."
                )

        return " ".join(parts)
