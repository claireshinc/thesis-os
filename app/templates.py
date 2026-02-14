"""
Sector templates — KPI packs, accounting adjustments, kill-criteria primitives,
and score inclusion/exclusion with reasons.

Each template tells the quant engine WHAT to compute for a given sector.
The engine knows HOW.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class KPIDefinition:
    id: str
    label: str
    unit: str  # "%", "$", "x", "days", "months"
    description: str  # includes source guidance
    alert_above: float | None = None
    alert_below: float | None = None
    alert_direction: str | None = None  # "declining_yoy", "declining_qoq", "context_dependent"


@dataclass
class AccountingAdjustment:
    name: str
    description: str
    computation: str  # human-readable formula


@dataclass
class KillCriterionTemplate:
    description: str
    metric: str  # KPI id
    operator: str
    threshold: float
    duration: str  # "1Q", "2Q", "1Y", etc.


@dataclass
class SectorTemplate:
    sector: str
    display_name: str
    primary_kpis: list[KPIDefinition]
    accounting_adjustments: list[AccountingAdjustment]
    default_kill_criteria: list[KillCriterionTemplate]
    primary_valuation: str  # "dcf", "ev_ebitda", "ev_revenue", "p_b_roe", "nav"
    valuation_notes: str
    include_scores: list[str]
    exclude_scores: list[str]
    exclude_reason: dict[str, str] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════
# SaaS / Cloud Software
# ═══════════════════════════════════════════════════════════════════════════

SAAS = SectorTemplate(
    sector="saas",
    display_name="SaaS / Cloud Software",
    primary_kpis=[
        KPIDefinition(
            "nrr",
            "Net Revenue Retention",
            "%",
            "Annual recurring revenue from existing customers YoY. "
            "Source: typically in 10-K revenue discussion or S-1. "
            "Not in XBRL — requires filing text extraction.",
            alert_below=105,
        ),
        KPIDefinition(
            "cac_payback",
            "CAC Payback Period",
            "months",
            "S&M spend / (net new ARR x gross margin). "
            "Compute from: 10-K SGA breakdown + ARR disclosure.",
            alert_above=24,
        ),
        KPIDefinition(
            "rule_of_40",
            "Rule of 40",
            "%",
            "Revenue growth % + FCF margin %. "
            "Source: computed from 10-K revenue + cash flow statement.",
            alert_below=30,
        ),
        KPIDefinition(
            "gross_margin",
            "Gross Margin",
            "%",
            "Source: 10-K income statement. "
            "Adjust: exclude SBC from COGS if material.",
            alert_below=70,
        ),
        KPIDefinition(
            "sbc_revenue",
            "SBC / Revenue",
            "%",
            "Stock-based compensation as % of revenue. "
            "Source: 10-K cash flow statement or compensation note.",
            alert_above=25,
        ),
        KPIDefinition(
            "fcf_margin",
            "FCF Margin",
            "%",
            "Free cash flow / revenue. "
            "Source: 10-K cash flow (operating CF - capex) / revenue.",
        ),
        KPIDefinition(
            "revenue_growth",
            "Revenue Growth YoY",
            "%",
            "Total revenue year-over-year growth. Source: 10-K income statement.",
        ),
    ],
    accounting_adjustments=[
        AccountingAdjustment(
            name="SBC normalization",
            description=(
                "SaaS companies often have SBC at 15-30% of revenue. "
                "FCF looks great but earnings are diluted. Always compute "
                "FCF-minus-SBC as the 'real' free cash flow."
            ),
            computation="adjusted_fcf = reported_fcf - sbc_expense",
        ),
        AccountingAdjustment(
            name="Capitalized software costs",
            description=(
                "Some SaaS companies capitalize development costs, "
                "inflating operating income. Check 10-K intangibles note."
            ),
            computation="adjusted_opex = reported_opex + capitalized_dev_costs",
        ),
    ],
    default_kill_criteria=[
        KillCriterionTemplate(
            "NRR < 105% for 2 consecutive quarters",
            "nrr", "<", 105, "2Q",
        ),
        KillCriterionTemplate(
            "CAC payback > 30 months",
            "cac_payback", ">", 30, "1Q",
        ),
        KillCriterionTemplate(
            "SBC/Revenue > 30% and rising",
            "sbc_revenue", ">", 30, "2Q",
        ),
        KillCriterionTemplate(
            "Rule of 40 < 25% for 2 consecutive quarters",
            "rule_of_40", "<", 25, "2Q",
        ),
    ],
    primary_valuation="ev_revenue",
    valuation_notes=(
        "EV/Revenue or EV/NTM Revenue is primary. "
        "DCF works but terminal value dominates — use with caution. "
        "Always pair with Rule of 40 to judge if multiple is deserved."
    ),
    include_scores=["beneish_m"],
    exclude_scores=["altman_z", "piotroski_f", "greenblatt"],
    exclude_reason={
        "altman_z": (
            "Designed for manufacturing firms. Working capital and "
            "retained earnings ratios are meaningless for SaaS."
        ),
        "piotroski_f": (
            "Asset turnover and leverage metrics don't apply. "
            "SaaS is asset-light with negative working capital by design."
        ),
        "greenblatt": (
            "EBIT/EV is often negative for growth SaaS. "
            "Ranking by earnings yield would exclude the best companies."
        ),
    },
)


# ═══════════════════════════════════════════════════════════════════════════
# Semiconductors
# ═══════════════════════════════════════════════════════════════════════════

SEMIS = SectorTemplate(
    sector="semis",
    display_name="Semiconductors",
    primary_kpis=[
        KPIDefinition(
            "backlog",
            "Order Backlog",
            "$",
            "Unfilled orders. Source: 10-K order/backlog discussion "
            "or earnings release. Not in XBRL — requires filing text extraction.",
            alert_direction="declining_qoq",
        ),
        KPIDefinition(
            "gross_margin",
            "Gross Margin",
            "%",
            "Source: 10-K income statement. "
            "Critical to decompose: mix vs ASP vs utilization.",
        ),
        KPIDefinition(
            "book_to_bill",
            "Book-to-Bill Ratio",
            "x",
            "New orders / revenue. >1.0 = expanding. "
            "Source: earnings release or 10-Q. "
            "Not in XBRL — requires filing text extraction.",
            alert_below=0.9,
        ),
        KPIDefinition(
            "inventory_days",
            "Inventory Days",
            "days",
            "Inventory / (COGS/365). Rising inventory days = "
            "demand softening or channel stuffing. Source: 10-K.",
            alert_direction="context_dependent",
        ),
        KPIDefinition(
            "capex_intensity",
            "CapEx / Revenue",
            "%",
            "Capital intensity. Source: 10-K cash flow statement. "
            "Varies by fabless vs IDM.",
        ),
        KPIDefinition(
            "r_and_d_intensity",
            "R&D / Revenue",
            "%",
            "Innovation spend. Source: 10-K income statement.",
            alert_direction="context_dependent",
        ),
        KPIDefinition(
            "revenue_growth",
            "Revenue Growth YoY",
            "%",
            "Total revenue year-over-year growth. Source: 10-K income statement.",
        ),
    ],
    accounting_adjustments=[
        AccountingAdjustment(
            name="Cycle normalization",
            description=(
                "Semi earnings are deeply cyclical. Use mid-cycle "
                "margins (avg of last full cycle, typically 3-5 years) "
                "for valuation. Trailing P/E is misleading at cycle peaks/troughs."
            ),
            computation="normalized_eps = mid_cycle_margin x current_revenue / shares",
        ),
        AccountingAdjustment(
            name="Gross margin bridge",
            description=(
                "Decompose gross margin changes into: (1) product mix, "
                "(2) ASP changes, (3) utilization rate, (4) input costs. "
                "Management often provides this in earnings calls."
            ),
            computation="See earnings call transcript for management bridge",
        ),
    ],
    default_kill_criteria=[
        KillCriterionTemplate(
            "Backlog declines >15% QoQ",
            "backlog", "qoq_decline >", 15, "1Q",
        ),
        KillCriterionTemplate(
            "Book-to-bill < 0.85 for 2 consecutive quarters",
            "book_to_bill", "<", 0.85, "2Q",
        ),
        KillCriterionTemplate(
            "Inventory days > 120 and rising",
            "inventory_days", ">", 120, "2Q",
        ),
        KillCriterionTemplate(
            "Gross margin below mid-cycle average by >500bps",
            "gross_margin", "below_midcycle_bps >", 500, "2Q",
        ),
    ],
    primary_valuation="ev_ebitda",
    valuation_notes=(
        "EV/EBITDA on normalized (mid-cycle) earnings is primary. "
        "P/E on trailing is deceptive at cycle turns. "
        "For equipment companies (ASML, KLAC), backlog visibility "
        "justifies forward estimates. For commodity semis, "
        "use EV/normalized EBITDA through the cycle."
    ),
    include_scores=["piotroski_f", "beneish_m"],
    exclude_scores=["altman_z"],
    exclude_reason={
        "altman_z": (
            "Working capital fluctuates with inventory cycle. "
            "Would flag distress at cycle troughs when stocks are cheapest."
        ),
    },
)


# ---------------------------------------------------------------------------
# Registry — look up a template by sector key
# ---------------------------------------------------------------------------

SECTOR_TEMPLATES: dict[str, SectorTemplate] = {
    "saas": SAAS,
    "semis": SEMIS,
}


def get_template(sector: str) -> SectorTemplate:
    """Look up a sector template by key. Raises KeyError if not found."""
    return SECTOR_TEMPLATES[sector]
