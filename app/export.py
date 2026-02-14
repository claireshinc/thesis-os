"""
Export engine — markdown and PDF rendering of briefs and theses.

Provides:
  export_brief_markdown(ticker)   — generates brief, renders as markdown
  export_thesis_markdown(thesis_id, session) — fetches thesis, renders as markdown
  export_brief_pdf(ticker)        — generates brief, renders as PDF bytes
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.brief import DecisionBriefResponse, generate_brief
from app.db import Thesis


# ---------------------------------------------------------------------------
# Brief — Markdown
# ---------------------------------------------------------------------------


async def export_brief_markdown(
    ticker: str,
    sector_override: str | None = None,
) -> str:
    """Generate a Decision Brief and render it as clean markdown."""
    brief = await generate_brief(ticker, sector_override=sector_override)
    return _render_brief_md(brief)


def _fmt_dollars(v: float) -> str:
    """Format a dollar amount with commas and no decimals."""
    if abs(v) >= 1e9:
        return f"${v / 1e9:,.1f}B"
    if abs(v) >= 1e6:
        return f"${v / 1e6:,.1f}M"
    return f"${v:,.0f}"


def _render_brief_md(brief: DecisionBriefResponse) -> str:
    """Pure function: DecisionBriefResponse -> markdown string."""
    lines: list[str] = []

    # --- Header ---
    lines.append(f"# Decision Brief: {brief.ticker}")
    lines.append(f"**{brief.entity_name}** | {brief.sector_display_name}")
    lines.append(f"Generated: {brief.generated_at}")
    lines.append("")

    # --- Variant Perception ---
    lines.append("## Variant Perception")
    if brief.market_implied:
        mi = brief.market_implied
        ig = mi.implied_fcf_growth_10yr
        ig_str = f"{ig:.1%}" if ig is not None else "N/A"
        lines.append(f"- **Implied FCF growth (10yr)**: {ig_str}")
        lines.append(f"- **WACC**: {mi.wacc:.2%} ({mi.wacc_build})")
        lines.append(f"- **Enterprise Value**: {_fmt_dollars(mi.ev_used)}")
        lines.append(f"- **FCF used**: {_fmt_dollars(mi.fcf_used)}")
        lines.append(f"- **Terminal growth**: {mi.terminal_growth:.1%}")
        if mi.sensitivity:
            parts = []
            for k, v in mi.sensitivity.items():
                parts.append(f"{k}: {v:.1%}" if v is not None else f"{k}: N/A")
            lines.append(f"- **Sensitivity**: {', '.join(parts)}")
    else:
        lines.append("Market-implied data not available.")
    lines.append("")

    # --- EV Build ---
    lines.append("## Enterprise Value Build")
    ev = brief.ev_build
    lines.append(f"- Market Cap: {_fmt_dollars(ev.market_cap.value)}")
    lines.append(f"- Total Debt: {_fmt_dollars(ev.total_debt.value)}")
    lines.append(f"- Cash & Equivalents: {_fmt_dollars(ev.cash.value)}")
    lines.append(f"- **Enterprise Value: {_fmt_dollars(ev.enterprise_value)}**")
    lines.append(f"- {ev.summary}")
    lines.append("")

    # --- Sector KPIs ---
    lines.append("## Sector KPIs")
    lines.append("")
    lines.append("| KPI | Value | Period | QoQ Delta | YoY Delta |")
    lines.append("|-----|-------|--------|-----------|-----------|")
    for kpi in brief.sector_kpis:
        val = f"{kpi.value:.2f}{kpi.unit}" if kpi.value is not None else "N/A"
        qoq = f"{kpi.qoq_delta:+.2f}" if kpi.qoq_delta is not None else "-"
        yoy = f"{kpi.yoy_delta:+.2f}" if kpi.yoy_delta is not None else "-"
        period = kpi.period or "-"
        lines.append(f"| {kpi.label} | {val} | {period} | {qoq} | {yoy} |")
    lines.append("")

    # --- Quality Scores ---
    if brief.quality_scores:
        lines.append("## Quality Scores")
        for score in brief.quality_scores:
            lines.append(f"- **{score.name}**: {score.value:.2f} — {score.interpretation}")
        lines.append("")

    if brief.excluded_scores:
        lines.append("### Excluded Scores")
        for name, reason in brief.excluded_scores.items():
            lines.append(f"- **{name}**: {reason}")
        lines.append("")

    # --- Holder Map ---
    lines.append("## Holder Map")
    hm = brief.holder_map
    if hm.holder_data_note:
        lines.append(f"> **Note**: {hm.holder_data_note}")
        lines.append("")
    lines.append(f"- **Total institutional holders**: {hm.holder_count}")
    if hm.top_holders:
        lines.append("")
        lines.append("| Holder | Type | Filing Date | Shares |")
        lines.append("|--------|------|-------------|--------|")
        for h in hm.top_holders[:10]:
            shares_str = f"{h.shares:,}" if h.shares else "-"
            lines.append(f"| {h.filer_name} | {h.fund_type} | {h.filing_date} | {shares_str} |")
    lines.append("")
    lines.append(f"**Insider summary**: {hm.insider_summary}")
    for k, v in hm.data_freshness.items():
        lines.append(f"- {k}: {v}")
    lines.append("")

    # --- Red Flags ---
    if brief.red_flags and brief.red_flags.red_flags:
        lines.append("## Red Flags")
        for rf in brief.red_flags.red_flags:
            lines.append(f"- **[{rf.severity.upper()}]** {rf.flag}")
            lines.append(f"  Section: {rf.section} | Evidence: {rf.evidence}")
            if rf.context:
                lines.append(f"  Context: {rf.context}")
        lines.append("")
        if brief.red_flags.clean_areas:
            lines.append(f"**Clean areas**: {', '.join(brief.red_flags.clean_areas)}")
            lines.append("")

    # --- Model Inputs ---
    lines.append("## Model Inputs")
    mi = brief.model_inputs
    if mi.wacc is not None:
        lines.append(f"- WACC: {mi.wacc:.2%}")
    lines.append(f"- Risk-free rate: {mi.risk_free_rate:.2%}" if mi.risk_free_rate else "- Risk-free rate: N/A")
    lines.append(f"- Beta: {mi.beta:.2f}")
    lines.append(f"- Equity risk premium: {mi.equity_risk_premium:.2%}")
    lines.append(f"- Terminal growth: {mi.terminal_growth:.1%}")
    lines.append(f"- Sector template: {mi.sector_template}")
    if mi.filing_used:
        lines.append(f"- Filing used: {mi.filing_used} ({mi.filing_date or 'date unknown'})")
    for k, v in mi.data_freshness.items():
        lines.append(f"- {k}: {v}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Thesis — Markdown
# ---------------------------------------------------------------------------


async def export_thesis_markdown(
    thesis_id: uuid.UUID,
    session: AsyncSession,
) -> str:
    """Fetch a thesis from the database and render it as markdown."""
    thesis = await crud.get_thesis(session, thesis_id)
    if thesis is None:
        raise ValueError(f"Thesis {thesis_id} not found")
    return _render_thesis_md(thesis)


def _render_thesis_md(thesis: Thesis) -> str:
    """Pure function: Thesis ORM object -> markdown string."""
    lines: list[str] = []

    # --- Header ---
    lines.append(f"# Thesis: {thesis.ticker} ({thesis.direction.upper()})")
    lines.append(f"**Status**: {thesis.status} | **Sector**: {thesis.sector_template}")
    lines.append(f"Created: {thesis.created_at.strftime('%Y-%m-%d %H:%M UTC')}")
    if thesis.entry_price is not None:
        lines.append(f"Entry: ${float(thesis.entry_price):,.2f} on {thesis.entry_date}")
    if thesis.close_price is not None:
        lines.append(f"Close: ${float(thesis.close_price):,.2f} on {thesis.close_date} — {thesis.close_reason}")
    lines.append("")

    # --- Thesis Statement ---
    lines.append("## Thesis")
    lines.append(thesis.thesis_text)
    lines.append("")

    # --- Claims Table ---
    if thesis.claims:
        lines.append("## Claims")
        lines.append("")
        lines.append("| ID | Statement | KPI | Current Value | Status |")
        lines.append("|----|-----------|-----|---------------|--------|")
        for c in thesis.claims:
            val = f"{float(c.current_value):.2f}" if c.current_value is not None else "N/A"
            lines.append(f"| {c.id} | {c.statement} | {c.kpi_id} | {val} | {c.status} |")
        lines.append("")

    # --- Kill Criteria ---
    if thesis.kill_criteria:
        lines.append("## Kill Criteria")
        lines.append("")
        for kc in thesis.kill_criteria:
            status_icon = {"ok": "OK", "watch": "WATCH", "breach": "BREACH"}.get(kc.status, kc.status)
            distance = f"{float(kc.distance_pct):.1f}%" if kc.distance_pct is not None else "-"
            current = f"{float(kc.current_value):.2f}" if kc.current_value is not None else "N/A"
            lines.append(f"- **{kc.id}**: {kc.description}")
            lines.append(f"  Metric: {kc.metric} {kc.operator} {float(kc.threshold):.2f} "
                         f"(duration: {kc.duration or 'N/A'})")
            lines.append(f"  Current: {current} | Status: {status_icon} | Distance: {distance}")
            if kc.watch_reason:
                lines.append(f"  Watch reason: {kc.watch_reason}")
        lines.append("")

    # --- Catalyst Calendar ---
    if thesis.catalysts:
        lines.append("## Catalyst Calendar")
        lines.append("")
        lines.append("| Date | Event | Claims Tested | Occurred |")
        lines.append("|------|-------|---------------|----------|")
        for cat in sorted(thesis.catalysts, key=lambda c: c.event_date):
            claims = ", ".join(cat.claims_tested) if cat.claims_tested else "-"
            occurred = "Yes" if cat.occurred else "No"
            lines.append(f"| {cat.event_date} | {cat.event} | {claims} | {occurred} |")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Brief — PDF
# ---------------------------------------------------------------------------


async def export_brief_pdf(
    ticker: str,
    sector_override: str | None = None,
) -> bytes:
    """Generate a Decision Brief and render it as a PDF."""
    brief = await generate_brief(ticker, sector_override=sector_override)
    return _render_brief_pdf(brief)


def _render_brief_pdf(brief: DecisionBriefResponse) -> bytes:
    """Pure function: DecisionBriefResponse -> PDF bytes."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def title(text: str):
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, text, new_x="LMARGIN", new_y="NEXT")

    def section(text: str):
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)

    def body(text: str):
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, text, new_x="LMARGIN", new_y="NEXT")

    def row(cells: list[str], widths: list[int], bold: bool = False):
        pdf.set_font("Helvetica", "B" if bold else "", 8)
        for i, cell in enumerate(cells):
            pdf.cell(widths[i], 6, cell[:40], border=1)
        pdf.ln()

    # --- Header ---
    title(f"Decision Brief: {brief.ticker}")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"{brief.entity_name} | {brief.sector_display_name}",
             new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Generated: {brief.generated_at}", new_x="LMARGIN", new_y="NEXT")

    # --- Variant Perception ---
    section("Variant Perception")
    if brief.market_implied:
        mi = brief.market_implied
        ig = mi.implied_fcf_growth_10yr
        ig_str = f"{ig:.1%}" if ig is not None else "N/A"
        body(
            f"Implied FCF growth (10yr): {ig_str}\n"
            f"WACC: {mi.wacc:.2%} ({mi.wacc_build})\n"
            f"Enterprise Value: {_fmt_dollars(mi.ev_used)}\n"
            f"FCF used: {_fmt_dollars(mi.fcf_used)}\n"
            f"Terminal growth: {mi.terminal_growth:.1%}"
        )
    else:
        body("Market-implied data not available.")

    # --- EV Build ---
    section("Enterprise Value Build")
    ev = brief.ev_build
    body(
        f"Market Cap: {_fmt_dollars(ev.market_cap.value)}\n"
        f"Total Debt: {_fmt_dollars(ev.total_debt.value)}\n"
        f"Cash: {_fmt_dollars(ev.cash.value)}\n"
        f"Enterprise Value: {_fmt_dollars(ev.enterprise_value)}"
    )

    # --- Sector KPIs ---
    section("Sector KPIs")
    kpi_widths = [50, 25, 25, 30, 30]
    row(["KPI", "Value", "Period", "QoQ", "YoY"], kpi_widths, bold=True)
    for kpi in brief.sector_kpis:
        val = f"{kpi.value:.2f}{kpi.unit}" if kpi.value is not None else "N/A"
        qoq = f"{kpi.qoq_delta:+.2f}" if kpi.qoq_delta is not None else "-"
        yoy = f"{kpi.yoy_delta:+.2f}" if kpi.yoy_delta is not None else "-"
        period = kpi.period or "-"
        row([kpi.label, val, period, qoq, yoy], kpi_widths)

    # --- Quality Scores ---
    if brief.quality_scores:
        section("Quality Scores")
        for score in brief.quality_scores:
            body(f"{score.name}: {score.value:.2f} -- {score.interpretation}")

    # --- Holder Map ---
    section("Holder Map")
    hm = brief.holder_map
    body(f"Total institutional holders: {hm.holder_count}")
    if hm.top_holders:
        holder_widths = [60, 30, 30, 35]
        row(["Holder", "Type", "Filed", "Shares"], holder_widths, bold=True)
        for h in hm.top_holders[:10]:
            shares_str = f"{h.shares:,}" if h.shares else "-"
            row([h.filer_name[:30], h.fund_type, h.filing_date, shares_str], holder_widths)
    body(f"Insider summary: {hm.insider_summary}")

    # --- Red Flags ---
    if brief.red_flags and brief.red_flags.red_flags:
        section("Red Flags")
        for rf in brief.red_flags.red_flags:
            body(f"[{rf.severity.upper()}] {rf.flag}\n"
                 f"Section: {rf.section} | Evidence: {rf.evidence}")

    # --- Model Inputs ---
    section("Model Inputs")
    mi_model = brief.model_inputs
    parts = [f"Sector template: {mi_model.sector_template}"]
    if mi_model.wacc is not None:
        parts.append(f"WACC: {mi_model.wacc:.2%}")
    parts.append(f"Beta: {mi_model.beta:.2f}")
    parts.append(f"ERP: {mi_model.equity_risk_premium:.2%}")
    parts.append(f"Terminal growth: {mi_model.terminal_growth:.1%}")
    if mi_model.filing_used:
        parts.append(f"Filing: {mi_model.filing_used} ({mi_model.filing_date or 'N/A'})")
    body("\n".join(parts))

    return bytes(pdf.output())
