"""
Driver coverage — single source of truth for coverage computation.

Replaces duplicated logic in thesis.py and brief.py.  Each analytical
dimension now returns a rich DimensionCoverage with status, human-readable
reasons, and supporting artifact IDs.
"""

from __future__ import annotations

import types
from dataclasses import dataclass, field

from pydantic import BaseModel


# ═══════════════════════════════════════════════════════════════════════════
# Dataclasses (used internally by engines)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class DimensionCoverage:
    status: str  # "covered" | "partial" | "missing"
    reasons: list[str] = field(default_factory=list)
    supporting_artifacts: list[str] = field(default_factory=list)


@dataclass
class DriverCoverage:
    revenue_drivers: DimensionCoverage = field(default_factory=lambda: DimensionCoverage(status="missing"))
    retention: DimensionCoverage = field(default_factory=lambda: DimensionCoverage(status="missing"))
    pricing: DimensionCoverage = field(default_factory=lambda: DimensionCoverage(status="missing"))
    margin: DimensionCoverage = field(default_factory=lambda: DimensionCoverage(status="missing"))
    competition: DimensionCoverage = field(default_factory=lambda: DimensionCoverage(status="missing"))
    score: int = 0


# ═══════════════════════════════════════════════════════════════════════════
# Pydantic response models (used by API layer)
# ═══════════════════════════════════════════════════════════════════════════


class DimensionCoverageResponse(BaseModel):
    status: str
    reasons: list[str]
    supporting_artifacts: list[str]


class DriverCoverageResponse(BaseModel):
    revenue_drivers: DimensionCoverageResponse
    retention: DimensionCoverageResponse
    pricing: DimensionCoverageResponse
    margin: DimensionCoverageResponse
    competition: DimensionCoverageResponse
    score: int


# ═══════════════════════════════════════════════════════════════════════════
# KPI → dimension mapping
# ═══════════════════════════════════════════════════════════════════════════

COVERAGE_MAP: dict[str, list[str]] = {
    "revenue_drivers": ["revenue_growth", "rpo_growth", "deferred_rev_growth"],
    "retention": ["nrr", "deferred_rev_growth"],
    "pricing": ["subscription_mix", "gross_margin"],
    "margin": ["operating_margin", "r_and_d_intensity", "sm_revenue", "fcf_margin"],
    "competition": [],  # special: claims-aware (thesis) or leading-KPI-presence (brief)
}

# Leading KPIs used as a proxy for competition coverage in brief mode
_LEADING_KPIS = ["rpo_growth", "deferred_rev_growth", "nrr", "backlog", "book_to_bill"]


# ═══════════════════════════════════════════════════════════════════════════
# Core computation
# ═══════════════════════════════════════════════════════════════════════════


def _fmt_value(val: float | None, unit: str) -> str:
    """Format a KPI value for human display."""
    if val is None:
        return "N/A"
    if unit == "%":
        return f"{val:.1f}%"
    if unit == "$":
        if abs(val) >= 1e9:
            return f"${val / 1e9:.1f}B"
        if abs(val) >= 1e6:
            return f"${val / 1e6:.1f}M"
        return f"${val:,.0f}"
    if unit == "x":
        return f"{val:.1f}x"
    if unit == "days":
        return f"{val:.0f} days"
    return f"{val:.2f}{unit}"


def _fmt_delta(delta: float | None) -> str:
    if delta is None:
        return ""
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta:.1f}pp"


def compute_driver_coverage(
    kpis: dict,
    claims: list | None = None,
) -> DriverCoverage:
    """
    Compute rich coverage across 5 analytical dimensions.

    Parameters
    ----------
    kpis : dict[str, KPIResult]
        Sector KPI results (from QuantOutput or duck-typed SimpleNamespace).
    claims : list[CompiledClaim] | None
        If provided (thesis context), used for competition dimension.
        If None (brief context), falls back to leading-KPI presence.
    """
    coverage = DriverCoverage()

    def _evaluate_dimension(dim_name: str, kpi_ids: list[str]) -> DimensionCoverage:
        reasons: list[str] = []
        artifacts: list[str] = []

        for kid in kpi_ids:
            kpi = kpis.get(kid)
            if kpi is None:
                reasons.append(f"{kid}: not computed for this sector")
                continue

            label = getattr(kpi, "label", kid)
            val = getattr(kpi, "value", None)
            unit = getattr(kpi, "unit", "")

            if val is None:
                reasons.append(f"{label}: no data available")
                continue

            # Has data — build descriptive reason
            artifacts.append(kid)
            yoy = getattr(kpi, "yoy_delta", None)
            delta_str = f", {_fmt_delta(yoy)} YoY" if yoy is not None else ""
            reasons.append(f"{label}: {_fmt_value(val, unit)}{delta_str}")

        with_data = len(artifacts)
        if with_data == 0:
            status = "missing"
        elif with_data < len(kpi_ids):
            status = "partial"
        else:
            status = "covered"

        return DimensionCoverage(status=status, reasons=reasons, supporting_artifacts=artifacts)

    coverage.revenue_drivers = _evaluate_dimension("revenue_drivers", COVERAGE_MAP["revenue_drivers"])
    coverage.retention = _evaluate_dimension("retention", COVERAGE_MAP["retention"])
    coverage.pricing = _evaluate_dimension("pricing", COVERAGE_MAP["pricing"])
    coverage.margin = _evaluate_dimension("margin", COVERAGE_MAP["margin"])

    # Competition dimension — context-dependent
    if claims is not None:
        # Thesis mode: at least 1 claim references a leading indicator
        has_leading_claim = any(
            getattr(c, "kpi_family", "") == "leading" for c in claims
        )
        if has_leading_claim:
            leading_ids = [c.kpi_id for c in claims if getattr(c, "kpi_family", "") == "leading"]
            coverage.competition = DimensionCoverage(
                status="covered",
                reasons=[f"Leading indicator claim on: {', '.join(leading_ids)}"],
                supporting_artifacts=leading_ids,
            )
        else:
            coverage.competition = DimensionCoverage(
                status="missing",
                reasons=["No claims reference leading indicators"],
                supporting_artifacts=[],
            )
    else:
        # Brief mode: check if any leading KPIs have data
        leading_with_data = [
            kid for kid in _LEADING_KPIS
            if kid in kpis and getattr(kpis[kid], "value", None) is not None
        ]
        if leading_with_data:
            coverage.competition = DimensionCoverage(
                status="covered",
                reasons=[f"Leading KPIs with data: {', '.join(leading_with_data)}"],
                supporting_artifacts=leading_with_data,
            )
        else:
            coverage.competition = DimensionCoverage(
                status="missing",
                reasons=["No leading KPI data available"],
                supporting_artifacts=[],
            )

    # Score: count of covered dimensions
    dims = [
        coverage.revenue_drivers, coverage.retention, coverage.pricing,
        coverage.margin, coverage.competition,
    ]
    coverage.score = sum(1 for d in dims if d.status == "covered")

    return coverage


# ═══════════════════════════════════════════════════════════════════════════
# Conversion helpers
# ═══════════════════════════════════════════════════════════════════════════


def _dim_to_response(dim: DimensionCoverage) -> DimensionCoverageResponse:
    return DimensionCoverageResponse(
        status=dim.status,
        reasons=dim.reasons,
        supporting_artifacts=dim.supporting_artifacts,
    )


def coverage_to_response(cov: DriverCoverage) -> DriverCoverageResponse:
    """Convert a DriverCoverage dataclass to its Pydantic response model."""
    return DriverCoverageResponse(
        revenue_drivers=_dim_to_response(cov.revenue_drivers),
        retention=_dim_to_response(cov.retention),
        pricing=_dim_to_response(cov.pricing),
        margin=_dim_to_response(cov.margin),
        competition=_dim_to_response(cov.competition),
        score=cov.score,
    )


def coverage_to_dict(cov: DriverCoverage) -> dict:
    """Convert a DriverCoverage dataclass to a plain dict (for _draft_to_dict)."""
    def _dim(d: DimensionCoverage) -> dict:
        return {
            "status": d.status,
            "reasons": d.reasons,
            "supporting_artifacts": d.supporting_artifacts,
        }

    return {
        "revenue_drivers": _dim(cov.revenue_drivers),
        "retention": _dim(cov.retention),
        "pricing": _dim(cov.pricing),
        "margin": _dim(cov.margin),
        "competition": _dim(cov.competition),
        "score": cov.score,
    }


def compute_coverage_from_claims(claims: list) -> DriverCoverageResponse:
    """
    Compute coverage from stored Claim ORM objects (for GET /thesis/{id}).

    Builds a minimal KPI-like dict from Claim fields so we can reuse
    compute_driver_coverage().
    """
    kpi_dict: dict = {}
    for c in claims:
        kpi_id = c.kpi_id
        if kpi_id not in kpi_dict:
            kpi_dict[kpi_id] = types.SimpleNamespace(
                kpi_id=kpi_id,
                label=kpi_id,
                value=float(c.current_value) if c.current_value is not None else None,
                unit="",
                period="",
                yoy_delta=float(c.yoy_delta) if c.yoy_delta is not None else None,
                qoq_delta=float(c.qoq_delta) if c.qoq_delta is not None else None,
            )

    # Build duck-typed claims for competition dimension
    claim_like = [
        types.SimpleNamespace(kpi_id=c.kpi_id, kpi_family=c.kpi_family)
        for c in claims
    ]

    cov = compute_driver_coverage(kpi_dict, claims=claim_like)
    return coverage_to_response(cov)
