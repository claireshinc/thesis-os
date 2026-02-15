"""
Decision Brief orchestrator — assembles a full brief for a single ticker.

Workflow:
  1. Resolve ticker → CIK + SIC → sector template (auto-detect or override).
  2. Fetch latest filing metadata for the qualitative engine.
  3. Run quant, flow, and qualitative engines in parallel via asyncio.gather.
  4. Assemble everything into a DecisionBrief with Pydantic response models.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.config import settings
from app.coverage import DriverCoverageResponse, compute_driver_coverage, coverage_to_response
from app.data import (
    SIC_TO_SECTOR,
    get_company_filings,
    get_company_submissions,
    get_segment_revenue,
)
from app.extraction import supplement_kpis_from_filings
from app.flow import FlowEngine, FlowOutput
from app.qualitative import QualitativeEngine, RedFlagReport
from app.quant import QuantEngine, QuantOutput
from app.templates import SECTOR_TEMPLATES, SectorTemplate, get_template

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Pydantic response models — serializable mirrors of engine dataclasses
# ═══════════════════════════════════════════════════════════════════════════


class SourceMetaResponse(BaseModel):
    source_type: str
    filer: str
    filing_date: str | None = None
    section: str | None = None
    accession_number: str | None = None
    url: str = ""
    description: str = ""


class EVComponentResponse(BaseModel):
    label: str
    value: float
    computation: str | None = None
    source: SourceMetaResponse


class EVBuildResponse(BaseModel):
    market_cap: EVComponentResponse
    total_debt: EVComponentResponse
    cash: EVComponentResponse
    enterprise_value: float
    summary: str


class MarketImpliedResponse(BaseModel):
    implied_fcf_growth_10yr: float | None = None  # None when reverse DCF has no solution
    wacc: float
    wacc_build: str
    fcf_used: float
    fcf_computation: str  # "FCF = OCF ($X) - CapEx ($Y) = $Z"
    ocf_used: float
    capex_used: float
    fcf_source: SourceMetaResponse
    ocf_source: SourceMetaResponse
    capex_source: SourceMetaResponse
    terminal_growth: float
    ev_used: float
    sensitivity: dict[str, float | None]
    # Consensus comparison
    consensus_revenue_growth: float | None = None
    consensus_eps: float | None = None
    consensus_source: str = "not available"
    company_guidance_revenue_growth: float | None = None
    company_guidance_source: str = "not extracted"


class TrendPointResponse(BaseModel):
    period: str
    value: float


class SegmentResponse(BaseModel):
    name: str
    revenue: float
    pct_of_total: float
    yoy_growth: float | None = None
    period: str


class KPIResponse(BaseModel):
    kpi_id: str
    label: str
    value: float | None = None
    unit: str
    period: str
    kpi_family: str = "lagging"  # "leading", "lagging", "efficiency", "quality"
    prior_value: float | None = None
    yoy_delta: float | None = None
    qoq_value: float | None = None
    qoq_prior: float | None = None
    qoq_delta: float | None = None
    qoq_period: str | None = None
    trend: list[TrendPointResponse] = Field(default_factory=list)
    source: SourceMetaResponse | None = None
    computation: str | None = None
    note: str | None = None


class ScoreResponse(BaseModel):
    name: str
    value: float
    interpretation: str
    components: dict[str, Any]
    source_periods: list[str]


class InsiderTransactionResponse(BaseModel):
    owner_name: str
    owner_title: str
    transaction_date: str
    transaction_type: str
    shares: float | None = None
    price_per_share: float | None = None
    value: float | None = None
    shares_owned_after: float | None = None
    is_10b5_1: bool
    is_discretionary: bool
    pct_of_holdings: float | None = None
    is_notable: bool
    context_note: str
    source: SourceMetaResponse
    transaction_count: int = 1


class HolderEntryResponse(BaseModel):
    filer_name: str
    form_type: str
    filing_date: str
    accession_number: str | None = None
    shares: int | None = None
    value: float | None = None
    fund_type: str = "unknown"


class HolderMapResponse(BaseModel):
    top_holders: list[HolderEntryResponse]
    holder_count: int
    insider_activity: list[InsiderTransactionResponse]
    insider_summary: str
    data_freshness: dict[str, str]
    holder_data_note: str = ""  # non-empty when data is stale or incomplete


class RedFlagResponse(BaseModel):
    flag: str
    severity: str
    section: str
    page: int | None = None
    page_unverified: bool = True
    evidence: str
    context: str
    source: SourceMetaResponse


class RedFlagReportResponse(BaseModel):
    red_flags: list[RedFlagResponse]
    clean_areas: list[str]
    filing_source: SourceMetaResponse


class ModelInputsResponse(BaseModel):
    """Transparent list of every assumption the brief relies on."""
    wacc: float | None = None
    risk_free_rate: float | None = None
    beta: float = 1.0
    equity_risk_premium: float = 0.045
    terminal_growth: float = 0.025
    sector_template: str
    filing_used: str | None = None
    filing_date: str | None = None
    data_freshness: dict[str, str] = Field(default_factory=dict)


class DecisionBriefResponse(BaseModel):
    ticker: str
    entity_name: str
    sector: str
    sector_display_name: str
    generated_at: str

    # Core quant
    ev_build: EVBuildResponse
    market_implied: MarketImpliedResponse | None = None
    sector_kpis: list[KPIResponse]
    quality_scores: list[ScoreResponse]
    excluded_scores: dict[str, str]

    # Segments
    segments: list[SegmentResponse] | None = None

    # Coverage
    driver_coverage: DriverCoverageResponse

    # Flow
    holder_map: HolderMapResponse

    # Qualitative
    red_flags: RedFlagReportResponse | None = None

    # Transparency
    model_inputs: ModelInputsResponse


# ═══════════════════════════════════════════════════════════════════════════
# Serialization helpers — convert engine dataclasses → Pydantic models
# ═══════════════════════════════════════════════════════════════════════════


def _src(source) -> SourceMetaResponse:
    """Convert a SourceMeta dataclass to its response model."""
    return SourceMetaResponse(
        source_type=source.source_type,
        filer=source.filer,
        filing_date=str(source.filing_date) if source.filing_date else None,
        section=source.section,
        accession_number=source.accession_number,
        url=source.url,
        description=source.description,
    )


def _serialize_ev(ev) -> EVBuildResponse:
    return EVBuildResponse(
        market_cap=EVComponentResponse(
            label=ev.market_cap.label, value=ev.market_cap.value,
            computation=ev.market_cap.computation, source=_src(ev.market_cap.source),
        ),
        total_debt=EVComponentResponse(
            label=ev.total_debt.label, value=ev.total_debt.value,
            computation=ev.total_debt.computation, source=_src(ev.total_debt.source),
        ),
        cash=EVComponentResponse(
            label=ev.cash.label, value=ev.cash.value,
            computation=ev.cash.computation, source=_src(ev.cash.source),
        ),
        enterprise_value=ev.enterprise_value,
        summary=ev.summary,
    )


def _nan_safe(v: float) -> float | None:
    """Convert NaN/inf to None for JSON serialization."""
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return v


def _serialize_implied(mi) -> MarketImpliedResponse | None:
    # If implied growth is NaN (no solution), still return the build info
    # but null out the unsolvable fields
    return MarketImpliedResponse(
        implied_fcf_growth_10yr=_nan_safe(mi.implied_fcf_growth_10yr),
        wacc=mi.wacc,
        wacc_build=mi.wacc_build,
        fcf_used=mi.fcf_used,
        fcf_computation=mi.fcf_computation,
        ocf_used=mi.ocf_used,
        capex_used=mi.capex_used,
        fcf_source=_src(mi.fcf_source),
        ocf_source=_src(mi.ocf_source),
        capex_source=_src(mi.capex_source),
        terminal_growth=mi.terminal_growth,
        ev_used=mi.ev_used,
        sensitivity={k: _nan_safe(v) for k, v in mi.sensitivity.items()},
        consensus_revenue_growth=mi.consensus_revenue_growth,
        consensus_eps=mi.consensus_eps,
        consensus_source=mi.consensus_source,
        company_guidance_revenue_growth=mi.company_guidance_revenue_growth,
        company_guidance_source=mi.company_guidance_source,
    )


def _serialize_kpis(kpis: dict, template: SectorTemplate) -> list[KPIResponse]:
    # Build family lookup from template
    family_map = {k.id: k.kpi_family for k in template.primary_kpis}
    out = []
    for kpi in kpis.values():
        out.append(KPIResponse(
            kpi_id=kpi.kpi_id, label=kpi.label, value=kpi.value, unit=kpi.unit,
            period=kpi.period, kpi_family=family_map.get(kpi.kpi_id, "lagging"),
            prior_value=kpi.prior_value, yoy_delta=kpi.yoy_delta,
            qoq_value=kpi.qoq_value, qoq_prior=kpi.qoq_prior,
            qoq_delta=kpi.qoq_delta, qoq_period=kpi.qoq_period,
            trend=[
                TrendPointResponse(period=tp.period, value=tp.value)
                for tp in kpi.trend
            ],
            source=_src(kpi.source) if kpi.source else None,
            computation=kpi.computation, note=kpi.note,
        ))
    return out


def _serialize_scores(scores: dict) -> list[ScoreResponse]:
    return [
        ScoreResponse(
            name=s.name, value=s.value, interpretation=s.interpretation,
            components=s.components, source_periods=s.source_periods,
        )
        for s in scores.values()
    ]


def _serialize_holder_map(hm) -> HolderMapResponse:
    return HolderMapResponse(
        top_holders=[
            HolderEntryResponse(
                filer_name=h.filer_name, form_type=h.form_type,
                filing_date=h.filing_date, accession_number=h.accession_number,
                shares=h.shares, value=h.value, fund_type=h.fund_type,
            )
            for h in hm.top_holders
        ],
        holder_count=hm.holder_count,
        insider_activity=[
            InsiderTransactionResponse(
                owner_name=t.owner_name, owner_title=t.owner_title,
                transaction_date=t.transaction_date, transaction_type=t.transaction_type,
                shares=t.shares, price_per_share=t.price_per_share,
                value=t.value, shares_owned_after=t.shares_owned_after,
                is_10b5_1=t.is_10b5_1, is_discretionary=t.is_discretionary,
                pct_of_holdings=t.pct_of_holdings, is_notable=t.is_notable,
                context_note=t.context_note, source=_src(t.source),
                transaction_count=getattr(t, "transaction_count", 1),
            )
            for t in hm.insider_activity
        ],
        insider_summary=hm.insider_summary,
        data_freshness=hm.data_freshness,
        holder_data_note=getattr(hm, "holder_data_note", ""),
    )


def _serialize_red_flags(rf: RedFlagReport) -> RedFlagReportResponse:
    return RedFlagReportResponse(
        red_flags=[
            RedFlagResponse(
                flag=f.flag, severity=f.severity, section=f.section,
                page=f.page, page_unverified=f.page_unverified,
                evidence=f.evidence, context=f.context, source=_src(f.source),
            )
            for f in rf.red_flags
        ],
        clean_areas=rf.clean_areas,
        filing_source=_src(rf.filing_source),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Sector auto-detection
# ═══════════════════════════════════════════════════════════════════════════


async def detect_sector(ticker: str) -> tuple[str, SectorTemplate, dict]:
    """
    Resolve ticker → SIC code → sector template.

    Returns (sector_key, template, submission_metadata).
    Falls back to the "general" template when the SIC code has no
    specialized mapping.
    """
    sub = await get_company_submissions(ticker)
    meta = sub.data
    sector_key = meta.get("sector_key")

    if sector_key is None:
        logger.info(
            "No specialized template for SIC %s (%s) — using general",
            meta["sic"], meta["sic_description"],
        )
        sector_key = "general"

    return sector_key, get_template(sector_key), meta


# ═══════════════════════════════════════════════════════════════════════════
# Brief orchestrator
# ═══════════════════════════════════════════════════════════════════════════


async def generate_brief(
    ticker: str,
    sector_override: str | None = None,
) -> DecisionBriefResponse:
    """
    Full Decision Brief for a single ticker.

    1. Auto-detect sector (or use override).
    2. Fetch latest 10-K filing metadata for qualitative analysis.
    3. Run quant + flow + qualitative in parallel.
    4. Assemble and return a serializable DecisionBriefResponse.
    """
    ticker = ticker.upper()

    # --- 1. Sector resolution ---
    if sector_override:
        template = get_template(sector_override)
        sector_key = sector_override
        sub_result = await get_company_submissions(ticker)
        sub_meta = sub_result.data
    else:
        sector_key, template, sub_meta = await detect_sector(ticker)

    cik = sub_meta["cik"]

    # --- 2. Fetch latest filing metadata (for qualitative engine) ---
    filing_meta: dict | None = None
    try:
        filings_result = await get_company_filings(
            ticker, form_types=["10-K", "10-K/A"], limit=1,
        )
        if filings_result.data:
            filing_meta = filings_result.data[0]
    except Exception as exc:
        logger.warning("Failed to fetch filing metadata for %s: %s", ticker, exc)

    # --- 3. Run engines in parallel ---
    quant_engine = QuantEngine()
    flow_engine = FlowEngine()

    # Build tasks — quant and flow always run
    quant_task = quant_engine.analyze(ticker, template)
    flow_task = flow_engine.analyze(ticker)

    # Qualitative only runs if we have a filing AND an API key
    qual_task: asyncio.Task | None = None
    if filing_meta and settings.anthropic_api_key:
        try:
            qual_engine = QualitativeEngine()
            qual_task = qual_engine.detect_red_flags(
                ticker,
                template,
                filing_meta["form_type"],
                filing_meta["accession_number"],
                cik,
            )
        except ValueError:
            logger.warning("Qualitative engine unavailable (no API key)")

    # Segment revenue runs in parallel with everything else
    segment_task = get_segment_revenue(ticker)

    # Gather — all engines run concurrently
    if qual_task:
        quant_out, flow_out, red_flag_out, segment_result = await asyncio.gather(
            quant_task, flow_task, qual_task, segment_task,
            return_exceptions=True,
        )
    else:
        results = await asyncio.gather(
            quant_task, flow_task, segment_task,
            return_exceptions=True,
        )
        quant_out, flow_out, segment_result = results
        red_flag_out = None

    # Handle engine failures gracefully
    if isinstance(quant_out, Exception):
        logger.error("Quant engine failed for %s: %s", ticker, quant_out)
        raise quant_out

    if isinstance(flow_out, Exception):
        logger.error("Flow engine failed for %s: %s", ticker, flow_out)
        raise flow_out

    if isinstance(red_flag_out, Exception):
        logger.warning("Qualitative engine failed for %s: %s", ticker, red_flag_out)
        red_flag_out = None

    # Segment revenue (best-effort — None if unavailable)
    segment_data = None
    if isinstance(segment_result, Exception):
        logger.warning("Segment revenue failed for %s: %s", ticker, segment_result)
    elif hasattr(segment_result, "data") and segment_result.data:
        segment_data = [
            SegmentResponse(
                name=s["name"], revenue=s["revenue"],
                pct_of_total=s["pct_of_total"],
                yoy_growth=s.get("yoy_growth"),
                period=s["period"],
            )
            for s in segment_result.data
        ]

    # --- 3b. Supplement KPIs from filing text (LLM extraction) ---
    try:
        quant_out = await supplement_kpis_from_filings(
            ticker, template, quant_out, cik,
        )
    except Exception as exc:
        logger.warning("KPI supplement failed for %s: %s", ticker, exc)

    # --- 4. Assemble the brief ---

    # Data freshness aggregation
    freshness: dict[str, str] = {}
    if isinstance(flow_out, FlowOutput):
        freshness.update(flow_out.holder_map.data_freshness)
    if filing_meta:
        freshness["filing_analyzed"] = filing_meta.get("filing_date", "unknown")
        freshness["filing_type"] = filing_meta.get("form_type", "unknown")

    model_inputs = ModelInputsResponse(
        wacc=quant_out.market_implied.wacc if quant_out.market_implied else None,
        risk_free_rate=(
            quant_out.market_implied.wacc - QuantEngine.BETA * QuantEngine.ERP
            if quant_out.market_implied else None
        ),
        beta=QuantEngine.BETA,
        equity_risk_premium=QuantEngine.ERP,
        terminal_growth=QuantEngine.TERMINAL_GROWTH,
        sector_template=sector_key,
        filing_used=filing_meta.get("accession_number") if filing_meta else None,
        filing_date=filing_meta.get("filing_date") if filing_meta else None,
        data_freshness=freshness,
    )

    return DecisionBriefResponse(
        ticker=ticker,
        entity_name=quant_out.entity_name,
        sector=sector_key,
        sector_display_name=template.display_name,
        generated_at=datetime.utcnow().isoformat() + "Z",
        ev_build=_serialize_ev(quant_out.ev_build),
        market_implied=(
            _serialize_implied(quant_out.market_implied)
            if quant_out.market_implied else None
        ),
        sector_kpis=_serialize_kpis(quant_out.sector_kpis, template),
        quality_scores=_serialize_scores(quant_out.quality_scores),
        excluded_scores=quant_out.excluded_scores,
        segments=segment_data,
        driver_coverage=coverage_to_response(compute_driver_coverage(quant_out.sector_kpis)),
        holder_map=_serialize_holder_map(flow_out.holder_map),
        red_flags=(
            _serialize_red_flags(red_flag_out)
            if isinstance(red_flag_out, RedFlagReport) else None
        ),
        model_inputs=model_inputs,
    )
