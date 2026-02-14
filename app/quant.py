"""
Quant engine — EV builder, reverse DCF, sector KPI computation, quality scores.

Every computation carries a full audit trail: the numbers used, the filings
they came from, and the formula applied.  Uses data.py for all data fetching.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from scipy.optimize import brentq

from app.data import (
    DataResult,
    SourceMeta,
    get_company_facts,
    get_quote,
    get_treasury_yield,
)
from app.templates import SectorTemplate

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class EVComponent:
    label: str
    value: float
    source: SourceMeta
    computation: str | None = None


@dataclass
class EVBuild:
    market_cap: EVComponent
    total_debt: EVComponent
    cash: EVComponent
    enterprise_value: float
    components: list[EVComponent]
    summary: str  # human-readable audit trail


@dataclass
class MarketImplied:
    implied_fcf_growth_10yr: float  # 10yr constant FCF growth that equates DCF to EV
    wacc: float
    wacc_build: str  # "rf 4.1% + beta 1.0 x ERP 4.5% = 8.6%"
    fcf_used: float
    fcf_computation: str  # "FCF = OCF ($X) - CapEx ($Y) = $Z"
    ocf_used: float
    ocf_source: SourceMeta
    capex_used: float
    capex_source: SourceMeta
    fcf_source: SourceMeta  # combined citation
    terminal_growth: float
    ev_used: float
    sensitivity: dict[str, float]  # {"wacc +1%": growth, "wacc -1%": growth}


@dataclass
class KPIResult:
    kpi_id: str
    label: str
    value: float | None
    unit: str
    period: str  # "FY2025"
    prior_value: float | None = None
    yoy_delta: float | None = None
    qoq_value: float | None = None  # most recent quarter
    qoq_prior: float | None = None  # quarter before that
    qoq_delta: float | None = None
    qoq_period: str | None = None  # "Q3 FY2025"
    source: SourceMeta | None = None
    computation: str | None = None
    note: str | None = None  # e.g. "requires filing text extraction"


@dataclass
class ScoreResult:
    name: str
    value: float
    interpretation: str
    components: dict[str, Any]
    source_periods: list[str]


@dataclass
class QuantOutput:
    ticker: str
    entity_name: str
    template_name: str
    ev_build: EVBuild
    market_implied: MarketImplied | None
    sector_kpis: dict[str, KPIResult]
    quality_scores: dict[str, ScoreResult]
    excluded_scores: dict[str, str]
    computed_at: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Helpers for extracting values from parsed XBRL facts
# ---------------------------------------------------------------------------

def _val(facts: dict, field_name: str, idx: int = 0) -> float | None:
    """Get value at index *idx* (0 = most recent) from XBRL facts dict."""
    entries = facts.get(field_name, [])
    if idx < len(entries):
        return entries[idx]["value"]
    return None


def _entry(facts: dict, field_name: str, idx: int = 0) -> dict | None:
    """Get full entry dict at index *idx* from XBRL facts dict."""
    entries = facts.get(field_name, [])
    if idx < len(entries):
        return entries[idx]
    return None


def _safe_div(a: float | None, b: float | None) -> float | None:
    """Divide a/b, returning None if either is None or b is zero."""
    if a is None or b is None or b == 0:
        return None
    return a / b


def _source_from_entry(entry: dict | None, entity_name: str, cik: str) -> SourceMeta:
    """Build a SourceMeta from an XBRL fact entry."""
    if entry is None:
        return SourceMeta(source_type="unknown", filer=entity_name)
    accession = entry.get("accession", "")
    cik_num = cik.lstrip("0") or "0"
    acc_no_dashes = accession.replace("-", "")
    return SourceMeta(
        source_type=entry.get("form", "10-K"),
        filer=entity_name,
        filing_date=date.fromisoformat(entry["filed"]) if entry.get("filed") else None,
        accession_number=accession,
        url=(
            f"https://www.sec.gov/Archives/edgar/data/{cik_num}/"
            f"{acc_no_dashes}/{accession}-index.htm"
        ) if accession else "",
        description=f"{entry.get('xbrl_concept', '')} from {entry.get('form', '?')} FY{entry.get('fiscal_year', '?')}",
    )


def _fmt(value: float, prefix: str = "$") -> str:
    """Format a large number for human-readable display."""
    abs_val = abs(value)
    if abs_val >= 1e12:
        return f"{prefix}{value / 1e12:,.1f}T"
    if abs_val >= 1e9:
        return f"{prefix}{value / 1e9:,.1f}B"
    if abs_val >= 1e6:
        return f"{prefix}{value / 1e6:,.1f}M"
    return f"{prefix}{value:,.0f}"


# ---------------------------------------------------------------------------
# Reverse DCF math
# ---------------------------------------------------------------------------

def _dcf_value(g: float, fcf: float, wacc: float, terminal_g: float, years: int = 10) -> float:
    """Projected DCF enterprise value for a given constant growth rate *g*."""
    pv = 0.0
    projected_fcf = fcf
    for t in range(1, years + 1):
        projected_fcf *= (1 + g)
        pv += projected_fcf / (1 + wacc) ** t
    # Gordon growth terminal value
    terminal_fcf = projected_fcf * (1 + terminal_g)
    tv = terminal_fcf / (wacc - terminal_g)
    pv += tv / (1 + wacc) ** years
    return pv


def solve_implied_growth(
    ev: float, fcf: float, wacc: float, terminal_g: float = 0.025
) -> float:
    """Solve for the constant growth rate that equates DCF value to EV."""
    def objective(g: float) -> float:
        return _dcf_value(g, fcf, wacc, terminal_g) - ev
    # Search between -30% and +60% growth
    try:
        return brentq(objective, -0.30, 0.60, xtol=1e-6)
    except ValueError:
        # No root in range — EV implies growth outside -30%..+60%
        logger.warning("Reverse DCF: no solution in [-30%%, +60%%] range")
        return float("nan")


# ---------------------------------------------------------------------------
# Quarterly fact helpers
#
# IMPORTANT: XBRL flow items (revenue, income, cash flow) are CUMULATIVE
# year-to-date in 10-Q filings. Q1=$3B, Q2=$6B (=Q1+Q2), Q3=$9B (=Q1+Q2+Q3).
# Balance sheet items (assets, inventory) are point-in-time.
#
# _standalone_q() converts cumulative YTD → discrete quarter values.
# ---------------------------------------------------------------------------

# Fields that are cumulative YTD in 10-Q filings (flow items).
# Balance sheet fields are NOT cumulative — they're point-in-time snapshots.
_CUMULATIVE_FIELDS = frozenset({
    "revenue", "cost_of_revenue", "gross_profit", "operating_income",
    "net_income", "research_and_development", "sga", "sbc",
    "interest_expense", "income_tax", "depreciation_amortization",
    "operating_cash_flow", "capex", "dividends_paid", "share_repurchases",
})


def _qval(quarterly: dict, field_name: str, idx: int = 0) -> float | None:
    """Get raw value at index *idx* (0 = most recent quarter) from quarterly dict."""
    entries = quarterly.get(field_name, [])
    if idx < len(entries):
        return entries[idx]["value"]
    return None


def _qentry(quarterly: dict, field_name: str, idx: int = 0) -> dict | None:
    entries = quarterly.get(field_name, [])
    if idx < len(entries):
        return entries[idx]
    return None


def _standalone_q(quarterly: dict, field_name: str, idx: int = 0) -> float | None:
    """
    Get the STANDALONE quarter value for a field.

    For cumulative flow items (revenue, COGS, etc.), computes:
      Q3 standalone = Q3_cumulative - Q2_cumulative (same fiscal year)
      Q1 standalone = Q1_cumulative (no prior quarter to subtract)

    For balance sheet items, returns the raw value (already point-in-time).
    """
    if field_name not in _CUMULATIVE_FIELDS:
        return _qval(quarterly, field_name, idx)

    entries = quarterly.get(field_name, [])
    if idx >= len(entries):
        return None

    entry = entries[idx]
    val = entry["value"]
    fp = entry.get("fiscal_period", "")
    fy = entry.get("fiscal_year", 0)

    if fp == "Q1":
        return val  # Q1 cumulative IS the standalone value

    # Find the prior quarter in the same fiscal year
    prior_fp = {"Q2": "Q1", "Q3": "Q2"}.get(fp)
    if prior_fp is None:
        return val  # unknown period, return as-is

    for e in entries:
        if e.get("fiscal_year") == fy and e.get("fiscal_period") == prior_fp:
            return val - e["value"]

    # Can't find prior quarter — return None rather than misleading cumulative
    return None


def _standalone_qentry(quarterly: dict, field_name: str, idx: int = 0) -> dict | None:
    """Get the entry metadata for the quarter at idx."""
    return _qentry(quarterly, field_name, idx)


def _find_yago_q(quarterly: dict, field_name: str, idx: int = 0) -> float | None:
    """
    Find the STANDALONE value for the same quarter one year ago.

    E.g., if idx=0 is Q3 FY2026, find Q3 FY2025 and return its standalone value.
    """
    entries = quarterly.get(field_name, [])
    if idx >= len(entries):
        return None

    target = entries[idx]
    target_fp = target.get("fiscal_period", "")
    target_fy = target.get("fiscal_year", 0)
    prior_fy = target_fy - 1

    # Find the same quarter in prior year
    for i, e in enumerate(entries):
        if e.get("fiscal_year") == prior_fy and e.get("fiscal_period") == target_fp:
            return _standalone_q(quarterly, field_name, i)

    return None


def _qoq_margin(quarterly: dict, numerator_field: str, denominator_field: str) -> tuple[float | None, float | None, str | None]:
    """
    Compute a ratio KPI using STANDALONE quarter values for the two most
    recent quarters.  Returns (current_ratio, prior_ratio, period_label).
    """
    n0 = _standalone_q(quarterly, numerator_field, 0)
    n1 = _standalone_q(quarterly, numerator_field, 1)
    d0 = _standalone_q(quarterly, denominator_field, 0)
    d1 = _standalone_q(quarterly, denominator_field, 1)
    cur = _safe_div(n0, d0)
    prior = _safe_div(n1, d1)
    if cur is not None:
        cur *= 100
    if prior is not None:
        prior *= 100
    entry = _qentry(quarterly, numerator_field, 0) or _qentry(quarterly, denominator_field, 0)
    period = f"{entry.get('fiscal_period', '?')} FY{entry.get('fiscal_year', '?')}" if entry else None
    return cur, prior, period


# ---------------------------------------------------------------------------
# KPI computation dispatch
# ---------------------------------------------------------------------------

def _compute_kpi(
    kpi_id: str, facts: dict, entity_name: str, cik: str,
    quarterly: dict | None = None,
) -> KPIResult | None:
    """Compute a single KPI from XBRL facts. Returns None if not computable."""
    q = quarterly or {}

    # Gross margin
    if kpi_id == "gross_margin":
        gp = _val(facts, "gross_profit")
        rev = _val(facts, "revenue")
        if gp is None and rev is not None:
            cor = _val(facts, "cost_of_revenue")
            if cor is not None:
                gp = rev - cor
        val = _safe_div(gp, rev)
        if val is not None:
            val *= 100
        prior_gp = _val(facts, "gross_profit", 1)
        prior_rev = _val(facts, "revenue", 1)
        prior_val = _safe_div(prior_gp, prior_rev)
        if prior_val is not None:
            prior_val *= 100
        entry = _entry(facts, "gross_profit") or _entry(facts, "revenue")
        # QoQ
        qcur, qprior, qperiod = _qoq_margin(q, "gross_profit", "revenue")
        return KPIResult(
            kpi_id="gross_margin", label="Gross Margin", value=val, unit="%",
            period=f"FY{entry.get('fiscal_year', '?')}" if entry else "?",
            prior_value=prior_val,
            yoy_delta=round(val - prior_val, 2) if val is not None and prior_val is not None else None,
            qoq_value=round(qcur, 2) if qcur is not None else None,
            qoq_prior=round(qprior, 2) if qprior is not None else None,
            qoq_delta=round(qcur - qprior, 2) if qcur is not None and qprior is not None else None,
            qoq_period=qperiod,
            source=_source_from_entry(entry, entity_name, cik),
            computation=f"gross_profit ({_fmt(gp or 0)}) / revenue ({_fmt(rev or 0)})",
        )

    # Revenue growth YoY
    if kpi_id == "revenue_growth":
        rev_0 = _val(facts, "revenue", 0)
        rev_1 = _val(facts, "revenue", 1)
        val = ((rev_0 / rev_1) - 1) * 100 if rev_0 and rev_1 and rev_1 != 0 else None
        entry = _entry(facts, "revenue")

        # QoQ: compare the YoY growth rate of the most recent quarter
        # to the YoY growth rate of the prior quarter.
        # E.g., Q3 FY2026 YoY growth = standalone_Q3_2026 / standalone_Q3_2025 - 1
        #        Q2 FY2026 YoY growth = standalone_Q2_2026 / standalone_Q2_2025 - 1
        # QoQ delta = Q3 growth - Q2 growth
        q0_standalone = _standalone_q(q, "revenue", 0)
        q0_yago = _find_yago_q(q, "revenue", 0)
        qgrowth = ((q0_standalone / q0_yago) - 1) * 100 if q0_standalone and q0_yago and q0_yago != 0 else None

        q1_standalone = _standalone_q(q, "revenue", 1)
        q1_yago = _find_yago_q(q, "revenue", 1)
        qgrowth_prior = ((q1_standalone / q1_yago) - 1) * 100 if q1_standalone and q1_yago and q1_yago != 0 else None

        qe = _qentry(q, "revenue", 0)
        qperiod = f"{qe.get('fiscal_period', '?')} FY{qe.get('fiscal_year', '?')}" if qe else None
        return KPIResult(
            kpi_id="revenue_growth", label="Revenue Growth YoY", value=round(val, 2) if val else None,
            unit="%", period=f"FY{entry.get('fiscal_year', '?')}" if entry else "?",
            qoq_value=round(qgrowth, 2) if qgrowth is not None else None,
            qoq_prior=round(qgrowth_prior, 2) if qgrowth_prior is not None else None,
            qoq_delta=round(qgrowth - qgrowth_prior, 2) if qgrowth is not None and qgrowth_prior is not None else None,
            qoq_period=qperiod,
            source=_source_from_entry(entry, entity_name, cik),
            computation=f"({_fmt(rev_0 or 0)} / {_fmt(rev_1 or 0)} - 1)" if rev_0 and rev_1 else None,
        )

    # SBC / Revenue
    if kpi_id == "sbc_revenue":
        sbc = _val(facts, "sbc")
        rev = _val(facts, "revenue")
        val = _safe_div(sbc, rev)
        if val is not None:
            val *= 100
        entry = _entry(facts, "sbc") or _entry(facts, "revenue")
        qcur, qprior, qperiod = _qoq_margin(q, "sbc", "revenue")
        return KPIResult(
            kpi_id="sbc_revenue", label="SBC / Revenue", value=round(val, 2) if val else None,
            unit="%", period=f"FY{entry.get('fiscal_year', '?')}" if entry else "?",
            qoq_value=round(qcur, 2) if qcur is not None else None,
            qoq_prior=round(qprior, 2) if qprior is not None else None,
            qoq_delta=round(qcur - qprior, 2) if qcur is not None and qprior is not None else None,
            qoq_period=qperiod,
            source=_source_from_entry(entry, entity_name, cik),
            computation=f"sbc ({_fmt(sbc or 0)}) / revenue ({_fmt(rev or 0)})" if sbc and rev else None,
        )

    # FCF margin
    if kpi_id == "fcf_margin":
        ocf = _val(facts, "operating_cash_flow")
        capex = _val(facts, "capex")
        rev = _val(facts, "revenue")
        fcf = (ocf - capex) if ocf is not None and capex is not None else None
        val = _safe_div(fcf, rev)
        if val is not None:
            val *= 100
        entry = _entry(facts, "operating_cash_flow") or _entry(facts, "revenue")
        # QoQ FCF margin — use standalone quarter values
        qocf0 = _standalone_q(q, "operating_cash_flow", 0)
        qocf1 = _standalone_q(q, "operating_cash_flow", 1)
        qcap0 = _standalone_q(q, "capex", 0)
        qcap1 = _standalone_q(q, "capex", 1)
        qrev0 = _standalone_q(q, "revenue", 0)
        qrev1 = _standalone_q(q, "revenue", 1)
        qfcf0 = (qocf0 - qcap0) if qocf0 is not None and qcap0 is not None else None
        qfcf1 = (qocf1 - qcap1) if qocf1 is not None and qcap1 is not None else None
        qcur = _safe_div(qfcf0, qrev0)
        qprior = _safe_div(qfcf1, qrev1)
        if qcur is not None:
            qcur *= 100
        if qprior is not None:
            qprior *= 100
        qe = _qentry(q, "operating_cash_flow", 0)
        qperiod = f"{qe.get('fiscal_period', '?')} FY{qe.get('fiscal_year', '?')}" if qe else None
        return KPIResult(
            kpi_id="fcf_margin", label="FCF Margin", value=round(val, 2) if val else None,
            unit="%", period=f"FY{entry.get('fiscal_year', '?')}" if entry else "?",
            qoq_value=round(qcur, 2) if qcur is not None else None,
            qoq_prior=round(qprior, 2) if qprior is not None else None,
            qoq_delta=round(qcur - qprior, 2) if qcur is not None and qprior is not None else None,
            qoq_period=qperiod,
            source=_source_from_entry(entry, entity_name, cik),
            computation=f"(OCF {_fmt(ocf or 0)} - capex {_fmt(capex or 0)}) / revenue {_fmt(rev or 0)}" if all([ocf, capex, rev]) else None,
        )

    # Rule of 40 (revenue growth + FCF margin)
    if kpi_id == "rule_of_40":
        rev_0 = _val(facts, "revenue", 0)
        rev_1 = _val(facts, "revenue", 1)
        ocf = _val(facts, "operating_cash_flow")
        capex = _val(facts, "capex")
        growth = ((rev_0 / rev_1) - 1) * 100 if rev_0 and rev_1 and rev_1 != 0 else None
        fcf = (ocf - capex) if ocf is not None and capex is not None else None
        fcf_margin = _safe_div(fcf, rev_0)
        if fcf_margin is not None:
            fcf_margin *= 100
        val = (growth + fcf_margin) if growth is not None and fcf_margin is not None else None
        entry = _entry(facts, "revenue")
        return KPIResult(
            kpi_id="rule_of_40", label="Rule of 40", value=round(val, 2) if val else None,
            unit="%", period=f"FY{entry.get('fiscal_year', '?')}" if entry else "?",
            source=_source_from_entry(entry, entity_name, cik),
            computation=f"rev_growth ({growth:.1f}%) + FCF_margin ({fcf_margin:.1f}%)" if growth is not None and fcf_margin is not None else None,
        )

    # Inventory days
    if kpi_id == "inventory_days":
        inv = _val(facts, "inventory")
        cogs = _val(facts, "cost_of_revenue")
        val = (inv / (cogs / 365)) if inv and cogs and cogs != 0 else None
        prior_inv = _val(facts, "inventory", 1)
        prior_cogs = _val(facts, "cost_of_revenue", 1)
        prior_val = (prior_inv / (prior_cogs / 365)) if prior_inv and prior_cogs and prior_cogs != 0 else None
        entry = _entry(facts, "inventory")
        # QoQ — inventory is point-in-time, but COGS is cumulative → use standalone
        qinv0, qinv1 = _qval(q, "inventory", 0), _qval(q, "inventory", 1)
        qcogs0 = _standalone_q(q, "cost_of_revenue", 0)
        qcogs1 = _standalone_q(q, "cost_of_revenue", 1)
        qval = (qinv0 / (qcogs0 * 4 / 365)) if qinv0 and qcogs0 and qcogs0 != 0 else None
        qval_prior = (qinv1 / (qcogs1 * 4 / 365)) if qinv1 and qcogs1 and qcogs1 != 0 else None
        qe = _qentry(q, "inventory", 0)
        qperiod = f"{qe.get('fiscal_period', '?')} FY{qe.get('fiscal_year', '?')}" if qe else None
        return KPIResult(
            kpi_id="inventory_days", label="Inventory Days", value=round(val, 1) if val else None,
            unit="days", period=f"FY{entry.get('fiscal_year', '?')}" if entry else "?",
            prior_value=round(prior_val, 1) if prior_val else None,
            yoy_delta=round(val - prior_val, 1) if val is not None and prior_val is not None else None,
            qoq_value=round(qval, 1) if qval is not None else None,
            qoq_prior=round(qval_prior, 1) if qval_prior is not None else None,
            qoq_delta=round(qval - qval_prior, 1) if qval is not None and qval_prior is not None else None,
            qoq_period=qperiod,
            source=_source_from_entry(entry, entity_name, cik),
            computation=f"inventory ({_fmt(inv or 0)}) / (COGS ({_fmt(cogs or 0)}) / 365)" if inv and cogs else None,
        )

    # CapEx / Revenue
    if kpi_id == "capex_intensity":
        capex = _val(facts, "capex")
        rev = _val(facts, "revenue")
        val = _safe_div(capex, rev)
        if val is not None:
            val *= 100
        entry = _entry(facts, "capex") or _entry(facts, "revenue")
        qcur, qprior, qperiod = _qoq_margin(q, "capex", "revenue")
        return KPIResult(
            kpi_id="capex_intensity", label="CapEx / Revenue", value=round(val, 2) if val else None,
            unit="%", period=f"FY{entry.get('fiscal_year', '?')}" if entry else "?",
            qoq_value=round(qcur, 2) if qcur is not None else None,
            qoq_prior=round(qprior, 2) if qprior is not None else None,
            qoq_delta=round(qcur - qprior, 2) if qcur is not None and qprior is not None else None,
            qoq_period=qperiod,
            source=_source_from_entry(entry, entity_name, cik),
            computation=f"capex ({_fmt(capex or 0)}) / revenue ({_fmt(rev or 0)})" if capex and rev else None,
        )

    # R&D / Revenue
    if kpi_id == "r_and_d_intensity":
        rnd = _val(facts, "research_and_development")
        rev = _val(facts, "revenue")
        val = _safe_div(rnd, rev)
        if val is not None:
            val *= 100
        entry = _entry(facts, "research_and_development") or _entry(facts, "revenue")
        qcur, qprior, qperiod = _qoq_margin(q, "research_and_development", "revenue")
        return KPIResult(
            kpi_id="r_and_d_intensity", label="R&D / Revenue", value=round(val, 2) if val else None,
            unit="%", period=f"FY{entry.get('fiscal_year', '?')}" if entry else "?",
            qoq_value=round(qcur, 2) if qcur is not None else None,
            qoq_prior=round(qprior, 2) if qprior is not None else None,
            qoq_delta=round(qcur - qprior, 2) if qcur is not None and qprior is not None else None,
            qoq_period=qperiod,
            source=_source_from_entry(entry, entity_name, cik),
            computation=f"R&D ({_fmt(rnd or 0)}) / revenue ({_fmt(rev or 0)})" if rnd and rev else None,
        )

    # Operating margin
    if kpi_id == "operating_margin":
        oi = _val(facts, "operating_income")
        rev = _val(facts, "revenue")
        val = _safe_div(oi, rev)
        if val is not None:
            val *= 100
        prior_oi = _val(facts, "operating_income", 1)
        prior_rev = _val(facts, "revenue", 1)
        prior_val = _safe_div(prior_oi, prior_rev)
        if prior_val is not None:
            prior_val *= 100
        entry = _entry(facts, "operating_income") or _entry(facts, "revenue")
        qcur, qprior, qperiod = _qoq_margin(q, "operating_income", "revenue")
        return KPIResult(
            kpi_id="operating_margin", label="Operating Margin", value=round(val, 2) if val is not None else None,
            unit="%", period=f"FY{entry.get('fiscal_year', '?')}" if entry else "?",
            prior_value=round(prior_val, 2) if prior_val is not None else None,
            yoy_delta=round(val - prior_val, 2) if val is not None and prior_val is not None else None,
            qoq_value=round(qcur, 2) if qcur is not None else None,
            qoq_prior=round(qprior, 2) if qprior is not None else None,
            qoq_delta=round(qcur - qprior, 2) if qcur is not None and qprior is not None else None,
            qoq_period=qperiod,
            source=_source_from_entry(entry, entity_name, cik),
            computation=f"operating_income ({_fmt(oi or 0)}) / revenue ({_fmt(rev or 0)})" if oi and rev else None,
        )

    # FCF yield (FCF / market cap proxy — uses EV if market cap unavailable)
    if kpi_id == "fcf_yield":
        ocf = _val(facts, "operating_cash_flow")
        capex = _val(facts, "capex")
        ta = _val(facts, "total_assets")
        fcf = (ocf - capex) if ocf is not None and capex is not None else None
        # Use total assets as a rough denominator — market cap isn't in XBRL
        val = _safe_div(fcf, ta)
        if val is not None:
            val *= 100
        entry = _entry(facts, "operating_cash_flow") or _entry(facts, "total_assets")
        return KPIResult(
            kpi_id="fcf_yield", label="FCF Yield (vs Total Assets)",
            value=round(val, 2) if val is not None else None,
            unit="%", period=f"FY{entry.get('fiscal_year', '?')}" if entry else "?",
            source=_source_from_entry(entry, entity_name, cik),
            computation=f"FCF ({_fmt(fcf or 0)}) / total_assets ({_fmt(ta or 0)})" if fcf and ta else None,
            note="Uses total assets as denominator — true FCF yield requires live market cap",
        )

    # Return on equity
    if kpi_id == "roe":
        ni = _val(facts, "net_income")
        eq = _val(facts, "total_equity")
        val = _safe_div(ni, eq)
        if val is not None:
            val *= 100
        prior_ni = _val(facts, "net_income", 1)
        prior_eq = _val(facts, "total_equity", 1)
        prior_val = _safe_div(prior_ni, prior_eq)
        if prior_val is not None:
            prior_val *= 100
        entry = _entry(facts, "net_income") or _entry(facts, "total_equity")
        return KPIResult(
            kpi_id="roe", label="Return on Equity", value=round(val, 2) if val is not None else None,
            unit="%", period=f"FY{entry.get('fiscal_year', '?')}" if entry else "?",
            prior_value=round(prior_val, 2) if prior_val is not None else None,
            yoy_delta=round(val - prior_val, 2) if val is not None and prior_val is not None else None,
            source=_source_from_entry(entry, entity_name, cik),
            computation=f"net_income ({_fmt(ni or 0)}) / total_equity ({_fmt(eq or 0)})" if ni and eq else None,
        )

    # Net Debt / EBITDA
    if kpi_id == "net_debt_ebitda":
        ltd = _val(facts, "long_term_debt") or 0
        std = _val(facts, "short_term_debt") or 0
        cash = _val(facts, "cash_and_equivalents") or 0
        sti = _val(facts, "short_term_investments") or 0
        net_debt = (ltd + std) - (cash + sti)
        oi = _val(facts, "operating_income") or 0
        da = _val(facts, "depreciation_amortization") or 0
        ebitda = oi + da
        val = net_debt / ebitda if ebitda != 0 else None
        entry = _entry(facts, "long_term_debt") or _entry(facts, "operating_income")
        return KPIResult(
            kpi_id="net_debt_ebitda", label="Net Debt / EBITDA",
            value=round(val, 2) if val is not None else None,
            unit="x", period=f"FY{entry.get('fiscal_year', '?')}" if entry else "?",
            source=_source_from_entry(entry, entity_name, cik),
            computation=(
                f"(debt {_fmt(ltd + std)} - cash {_fmt(cash + sti)}) / "
                f"(OI {_fmt(oi)} + D&A {_fmt(da)})"
            ) if ebitda != 0 else None,
        )

    # KPIs that require filing text extraction (not computable from XBRL)
    if kpi_id in ("nrr", "cac_payback", "backlog", "book_to_bill"):
        return KPIResult(
            kpi_id=kpi_id, label=kpi_id, value=None, unit="",
            period="?", note="Requires filing text extraction — not available in XBRL",
        )

    return None


# ---------------------------------------------------------------------------
# QuantEngine
# ---------------------------------------------------------------------------

class QuantEngine:
    """
    Runs quant analysis for a ticker against a sector template.

    Call: output = await QuantEngine().analyze("AAPL", saas_template)
    """

    # WACC parameters
    BETA = 1.0  # TODO: compute from price regression against S&P 500
    ERP = 0.045  # 4.5% equity risk premium — standard, barely moves
    TERMINAL_GROWTH = 0.025  # 2.5% long-run nominal GDP growth

    async def analyze(self, ticker: str, template: SectorTemplate) -> QuantOutput:
        # Fetch all data sources in parallel (include quarterly for QoQ deltas)
        facts_result, quote_result, treasury_result = await asyncio.gather(
            get_company_facts(ticker, include_quarterly=True),
            get_quote(ticker),
            get_treasury_yield(),
        )

        facts_data = facts_result.data
        facts = facts_data["facts"]
        quarterly = facts_data.get("quarterly", {})
        entity_name = facts_data["entity_name"]
        cik = facts_data["cik"]
        quote = quote_result.data
        risk_free = treasury_result.data["ten_year"]

        # --- EV Build ---
        ev_build = self._build_ev(facts, quote, entity_name, cik)

        # --- Reverse DCF ---
        market_implied = self._reverse_dcf(
            ev_build, facts, entity_name, cik, risk_free
        )

        # --- Sector KPIs (with QoQ deltas from quarterly data) ---
        sector_kpis = {}
        for kpi_def in template.primary_kpis:
            result = _compute_kpi(kpi_def.id, facts, entity_name, cik, quarterly)
            if result is not None:
                sector_kpis[kpi_def.id] = result

        # --- Quality Scores (only if template includes them) ---
        quality_scores = {}
        for score_name in template.include_scores:
            score = self._compute_score(score_name, facts, entity_name, cik)
            if score is not None:
                quality_scores[score_name] = score

        excluded = {
            name: template.exclude_reason.get(name, "Not applicable to this sector")
            for name in template.exclude_scores
        }

        return QuantOutput(
            ticker=ticker.upper(),
            entity_name=entity_name,
            template_name=template.display_name,
            ev_build=ev_build,
            market_implied=market_implied,
            sector_kpis=sector_kpis,
            quality_scores=quality_scores,
            excluded_scores=excluded,
        )

    # -------------------------------------------------------------------
    # EV Builder — every component gets a citation
    # -------------------------------------------------------------------

    def _build_ev(
        self, facts: dict, quote: dict, entity_name: str, cik: str,
    ) -> EVBuild:
        price = quote.get("price")
        shares = _val(facts, "shares_outstanding")
        shares_entry = _entry(facts, "shares_outstanding")

        # Market cap = price x shares_outstanding
        mkt_cap = price * shares if price and shares else None
        mkt_cap_comp = EVComponent(
            label="Market Cap",
            value=mkt_cap or 0,
            source=_source_from_entry(shares_entry, entity_name, cik),
            computation=f"price ({price}) x shares ({_fmt(shares or 0, '')})" if price and shares else "unavailable",
        )

        # Total debt = long-term debt + short-term debt
        ltd = _val(facts, "long_term_debt") or 0
        std = _val(facts, "short_term_debt") or 0
        total_debt = ltd + std
        debt_entry = _entry(facts, "long_term_debt") or _entry(facts, "short_term_debt")
        debt_comp = EVComponent(
            label="Total Debt",
            value=total_debt,
            source=_source_from_entry(debt_entry, entity_name, cik),
            computation=f"LT debt ({_fmt(ltd)}) + ST debt ({_fmt(std)})",
        )

        # Cash & equivalents (+ short-term investments if available)
        cash_val = _val(facts, "cash_and_equivalents") or 0
        sti = _val(facts, "short_term_investments") or 0
        total_cash = cash_val + sti
        cash_entry = _entry(facts, "cash_and_equivalents")
        cash_comp = EVComponent(
            label="Cash & Equivalents",
            value=total_cash,
            source=_source_from_entry(cash_entry, entity_name, cik),
            computation=f"cash ({_fmt(cash_val)}) + ST investments ({_fmt(sti)})",
        )

        ev = (mkt_cap or 0) + total_debt - total_cash

        summary = (
            f"EV = Market Cap ({_fmt(mkt_cap or 0)}) "
            f"+ Debt ({_fmt(total_debt)}) "
            f"- Cash ({_fmt(total_cash)}) "
            f"= {_fmt(ev)}"
        )

        return EVBuild(
            market_cap=mkt_cap_comp,
            total_debt=debt_comp,
            cash=cash_comp,
            enterprise_value=ev,
            components=[mkt_cap_comp, debt_comp, cash_comp],
            summary=summary,
        )

    # -------------------------------------------------------------------
    # Reverse DCF — solve for implied growth rate
    # -------------------------------------------------------------------

    def _reverse_dcf(
        self,
        ev_build: EVBuild,
        facts: dict,
        entity_name: str,
        cik: str,
        risk_free: float,
    ) -> MarketImplied | None:
        ocf = _val(facts, "operating_cash_flow")
        capex = _val(facts, "capex")
        if ocf is None or capex is None:
            logger.warning("Cannot compute reverse DCF: missing OCF or capex")
            return None

        fcf = ocf - capex
        if fcf <= 0:
            logger.warning("FCF is negative (%s), reverse DCF may not converge", _fmt(fcf))
            # Still attempt — brentq can handle negative FCF if EV is low enough

        ev = ev_build.enterprise_value
        wacc = risk_free + self.BETA * self.ERP
        wacc_build = (
            f"rf {risk_free:.2%} + beta {self.BETA:.1f} x ERP {self.ERP:.1%} "
            f"= {wacc:.2%}"
        )

        implied_g = solve_implied_growth(ev, fcf, wacc, self.TERMINAL_GROWTH)

        # Sensitivity: WACC +/- 1%
        sensitivity = {}
        for delta, label in [(0.01, "wacc +1%"), (-0.01, "wacc -1%")]:
            sensitivity[label] = solve_implied_growth(
                ev, fcf, wacc + delta, self.TERMINAL_GROWTH
            )

        # Separate citations for OCF and CapEx
        ocf_entry = _entry(facts, "operating_cash_flow")
        capex_entry = _entry(facts, "capex")
        ocf_source = _source_from_entry(ocf_entry, entity_name, cik)
        capex_source = _source_from_entry(capex_entry, entity_name, cik)

        # Combined FCF source with proper computation trail
        fcf_computation = (
            f"FCF = OCF ({_fmt(ocf)}) - CapEx ({_fmt(capex)}) = {_fmt(fcf)}"
        )
        fcf_source = SourceMeta(
            source_type=ocf_source.source_type,
            filer=entity_name,
            filing_date=ocf_source.filing_date,
            accession_number=ocf_source.accession_number,
            url=ocf_source.url,
            description=fcf_computation,
        )

        return MarketImplied(
            implied_fcf_growth_10yr=implied_g,
            wacc=wacc,
            wacc_build=wacc_build,
            fcf_used=fcf,
            fcf_computation=fcf_computation,
            ocf_used=ocf,
            ocf_source=ocf_source,
            capex_used=capex,
            capex_source=capex_source,
            fcf_source=fcf_source,
            terminal_growth=self.TERMINAL_GROWTH,
            ev_used=ev,
            sensitivity=sensitivity,
        )

    # -------------------------------------------------------------------
    # Quality scores dispatch
    # -------------------------------------------------------------------

    def _compute_score(
        self, name: str, facts: dict, entity_name: str, cik: str
    ) -> ScoreResult | None:
        if name == "piotroski_f":
            return self._piotroski_f(facts, entity_name, cik)
        if name == "beneish_m":
            return self._beneish_m(facts, entity_name, cik)
        logger.warning("Unknown score requested: %s", name)
        return None

    # -------------------------------------------------------------------
    # Piotroski F-Score (9 binary signals, 0-9)
    # -------------------------------------------------------------------

    def _piotroski_f(self, facts: dict, entity_name: str, cik: str) -> ScoreResult:
        signals: dict[str, int] = {}

        # --- Profitability (4 signals) ---
        ni = _val(facts, "net_income", 0)
        ta = _val(facts, "total_assets", 0)
        roa = _safe_div(ni, ta)
        signals["1_roa_positive"] = 1 if roa is not None and roa > 0 else 0

        ocf = _val(facts, "operating_cash_flow", 0)
        signals["2_ocf_positive"] = 1 if ocf is not None and ocf > 0 else 0

        ni_1 = _val(facts, "net_income", 1)
        ta_1 = _val(facts, "total_assets", 1)
        roa_prior = _safe_div(ni_1, ta_1)
        signals["3_roa_increasing"] = (
            1 if roa is not None and roa_prior is not None and roa > roa_prior else 0
        )

        signals["4_accruals_ocf_gt_ni"] = (
            1 if ocf is not None and ni is not None and ocf > ni else 0
        )

        # --- Leverage / Liquidity (3 signals) ---
        ltd = _val(facts, "long_term_debt", 0) or 0
        ltd_prior = _val(facts, "long_term_debt", 1) or 0
        signals["5_leverage_decreasing"] = 1 if ltd <= ltd_prior else 0

        ca = _val(facts, "current_assets", 0)
        cl = _val(facts, "current_liabilities", 0)
        ca_1 = _val(facts, "current_assets", 1)
        cl_1 = _val(facts, "current_liabilities", 1)
        cr = _safe_div(ca, cl)
        cr_prior = _safe_div(ca_1, cl_1)
        signals["6_current_ratio_increasing"] = (
            1 if cr is not None and cr_prior is not None and cr > cr_prior else 0
        )

        shares = _val(facts, "shares_outstanding", 0)
        shares_prior = _val(facts, "shares_outstanding", 1)
        signals["7_no_dilution"] = (
            1 if shares is not None and shares_prior is not None and shares <= shares_prior else 0
        )

        # --- Operating Efficiency (2 signals) ---
        gp = _val(facts, "gross_profit", 0)
        rev = _val(facts, "revenue", 0)
        gp_1 = _val(facts, "gross_profit", 1)
        rev_1 = _val(facts, "revenue", 1)
        gm = _safe_div(gp, rev)
        gm_prior = _safe_div(gp_1, rev_1)
        signals["8_gross_margin_increasing"] = (
            1 if gm is not None and gm_prior is not None and gm > gm_prior else 0
        )

        at = _safe_div(rev, ta)
        at_prior = _safe_div(rev_1, ta_1)
        signals["9_asset_turnover_increasing"] = (
            1 if at is not None and at_prior is not None and at > at_prior else 0
        )

        score = sum(signals.values())

        if score >= 7:
            interp = f"Strong ({score}/9): Improving profitability, leverage, and efficiency"
        elif score >= 4:
            interp = f"Moderate ({score}/9): Mixed fundamental signals"
        else:
            interp = f"Weak ({score}/9): Deteriorating fundamentals across multiple dimensions"

        # Determine which fiscal years were used
        entry_0 = _entry(facts, "revenue", 0)
        entry_1 = _entry(facts, "revenue", 1)
        periods = []
        if entry_0:
            periods.append(f"FY{entry_0.get('fiscal_year', '?')}")
        if entry_1:
            periods.append(f"FY{entry_1.get('fiscal_year', '?')}")

        return ScoreResult(
            name="Piotroski F-Score",
            value=score,
            interpretation=interp,
            components=signals,
            source_periods=periods,
        )

    # -------------------------------------------------------------------
    # Beneish M-Score (earnings manipulation probability)
    # -------------------------------------------------------------------

    def _beneish_m(self, facts: dict, entity_name: str, cik: str) -> ScoreResult:
        # Current (idx=0) and prior year (idx=1)
        rev_0 = _val(facts, "revenue", 0) or 0
        rev_1 = _val(facts, "revenue", 1) or 0
        recv_0 = _val(facts, "accounts_receivable", 0) or 0
        recv_1 = _val(facts, "accounts_receivable", 1) or 0
        gp_0 = _val(facts, "gross_profit", 0) or 0
        gp_1 = _val(facts, "gross_profit", 1) or 0
        ta_0 = _val(facts, "total_assets", 0) or 0
        ta_1 = _val(facts, "total_assets", 1) or 0
        ca_0 = _val(facts, "current_assets", 0) or 0
        ca_1 = _val(facts, "current_assets", 1) or 0
        ppe_0 = _val(facts, "property_plant_equipment", 0) or 0
        ppe_1 = _val(facts, "property_plant_equipment", 1) or 0
        da_0 = _val(facts, "depreciation_amortization", 0) or 0
        da_1 = _val(facts, "depreciation_amortization", 1) or 0
        sga_0 = _val(facts, "sga", 0) or 0
        sga_1 = _val(facts, "sga", 1) or 0
        ni_0 = _val(facts, "net_income", 0) or 0
        ocf_0 = _val(facts, "operating_cash_flow", 0) or 0
        tl_0 = _val(facts, "total_liabilities", 0) or 0
        tl_1 = _val(facts, "total_liabilities", 1) or 0

        # DSRI — Days Sales in Receivables Index
        dsr_0 = recv_0 / rev_0 if rev_0 else 0
        dsr_1 = recv_1 / rev_1 if rev_1 else 0
        dsri = dsr_0 / dsr_1 if dsr_1 else 1.0

        # GMI — Gross Margin Index
        gm_0 = gp_0 / rev_0 if rev_0 else 0
        gm_1 = gp_1 / rev_1 if rev_1 else 0
        gmi = gm_1 / gm_0 if gm_0 else 1.0

        # AQI — Asset Quality Index
        aq_0 = 1 - (ca_0 + ppe_0) / ta_0 if ta_0 else 0
        aq_1 = 1 - (ca_1 + ppe_1) / ta_1 if ta_1 else 0
        aqi = aq_0 / aq_1 if aq_1 else 1.0

        # SGI — Sales Growth Index
        sgi = rev_0 / rev_1 if rev_1 else 1.0

        # DEPI — Depreciation Index
        dep_rate_0 = da_0 / (da_0 + ppe_0) if (da_0 + ppe_0) else 0
        dep_rate_1 = da_1 / (da_1 + ppe_1) if (da_1 + ppe_1) else 0
        depi = dep_rate_1 / dep_rate_0 if dep_rate_0 else 1.0

        # SGAI — SGA Expense Index
        sga_rev_0 = sga_0 / rev_0 if rev_0 else 0
        sga_rev_1 = sga_1 / rev_1 if rev_1 else 0
        sgai = sga_rev_0 / sga_rev_1 if sga_rev_1 else 1.0

        # TATA — Total Accruals to Total Assets
        tata = (ni_0 - ocf_0) / ta_0 if ta_0 else 0

        # LVGI — Leverage Index
        lev_0 = tl_0 / ta_0 if ta_0 else 0
        lev_1 = tl_1 / ta_1 if ta_1 else 0
        lvgi = lev_0 / lev_1 if lev_1 else 1.0

        # Beneish M-Score formula
        m = (
            -4.84
            + 0.920 * dsri
            + 0.528 * gmi
            + 0.404 * aqi
            + 0.892 * sgi
            + 0.115 * depi
            - 0.172 * sgai
            + 4.679 * tata
            - 0.327 * lvgi
        )

        if m > -1.78:
            interp = f"M-Score {m:.2f} > -1.78: Higher probability of earnings manipulation"
        else:
            interp = f"M-Score {m:.2f} < -1.78: Lower probability of earnings manipulation"

        entry_0 = _entry(facts, "revenue", 0)
        entry_1 = _entry(facts, "revenue", 1)
        periods = []
        if entry_0:
            periods.append(f"FY{entry_0.get('fiscal_year', '?')}")
        if entry_1:
            periods.append(f"FY{entry_1.get('fiscal_year', '?')}")

        return ScoreResult(
            name="Beneish M-Score",
            value=round(m, 2),
            interpretation=interp,
            components={
                "DSRI": round(dsri, 3),
                "GMI": round(gmi, 3),
                "AQI": round(aqi, 3),
                "SGI": round(sgi, 3),
                "DEPI": round(depi, 3),
                "SGAI": round(sgai, 3),
                "TATA": round(tata, 3),
                "LVGI": round(lvgi, 3),
            },
            source_periods=periods,
        )
