"""
Filing supplement bridge — fills KPI gaps by extracting values from filing text.

Called after the quant engine runs. Checks which KPIs have value=None and an
extraction_hint set on their template definition. If any need extraction, calls
the qualitative engine's extract_structured_kpis() method.

Avoids circular imports: quant.py → data.py, qualitative.py → data.py,
this module bridges them without either importing the other.
"""

from __future__ import annotations

import logging
from datetime import date

from app.config import settings
from app.data import SourceMeta, get_company_filings
from app.qualitative import QualitativeEngine
from app.quant import KPIResult, QuantOutput
from app.templates import SectorTemplate

logger = logging.getLogger(__name__)


async def supplement_kpis_from_filings(
    ticker: str,
    template: SectorTemplate,
    quant_output: QuantOutput,
    cik: str,
) -> QuantOutput:
    """
    Fill KPI gaps using LLM extraction from the latest filing.

    Checks which KPIs in the template have:
      1. value=None in quant_output.sector_kpis (or missing entirely)
      2. extraction_hint set in the template definition

    If none need extraction, returns immediately (no LLM cost).
    Otherwise, fetches the latest 10-K and extracts the missing values.
    """
    if not settings.anthropic_api_key:
        logger.info("No API key — skipping filing supplement")
        return quant_output

    # Build list of KPIs that need extraction
    kpi_requests: list[dict] = []
    for kpi_def in template.primary_kpis:
        if kpi_def.extraction_hint is None:
            continue
        existing = quant_output.sector_kpis.get(kpi_def.id)
        if existing is not None and existing.value is not None:
            continue  # Already has data from XBRL
        kpi_requests.append({
            "kpi_id": kpi_def.id,
            "label": kpi_def.label,
            "hint": kpi_def.extraction_hint,
        })

    if not kpi_requests:
        return quant_output

    logger.info(
        "Supplementing %d KPIs from filing text for %s: %s",
        len(kpi_requests),
        ticker,
        [r["kpi_id"] for r in kpi_requests],
    )

    # Find the latest 10-K filing
    try:
        filings_result = await get_company_filings(
            ticker, form_types=["10-K", "10-K/A"], limit=1,
        )
        if not filings_result.data:
            logger.warning("No 10-K filings found for %s — skipping extraction", ticker)
            return quant_output

        filing = filings_result.data[0]

        engine = QualitativeEngine()
        extracted = await engine.extract_structured_kpis(
            ticker=ticker,
            kpi_requests=kpi_requests,
            form_type=filing["form_type"],
            accession_number=filing["accession_number"],
            cik=filing["cik"],
        )
    except Exception as exc:
        logger.warning("Filing extraction failed for %s: %s", ticker, exc)
        return quant_output

    # Merge extracted values back into quant_output
    for item in extracted:
        kpi_id = item.get("kpi_id", "")
        value = item.get("value")
        if kpi_id and value is not None:
            # Find the template definition for label/unit
            kpi_def = next(
                (k for k in template.primary_kpis if k.id == kpi_id), None,
            )
            if kpi_def is None:
                continue

            confidence = item.get("confidence", "low")
            note_parts = [f"Extracted from filing ({confidence} confidence)"]
            if item.get("note"):
                note_parts.append(item["note"])

            quant_output.sector_kpis[kpi_id] = KPIResult(
                kpi_id=kpi_id,
                label=kpi_def.label,
                value=value,
                unit=kpi_def.unit,
                period=item.get("period", "?"),
                source=SourceMeta(
                    source_type=filing["form_type"],
                    filer=ticker.upper(),
                    filing_date=(
                        date.fromisoformat(filing["filing_date"])
                        if filing.get("filing_date") else None
                    ),
                    accession_number=filing["accession_number"],
                    url=filing.get("url", ""),
                    description=f"Extracted from {filing['form_type']}: {item.get('exact_quote', '')[:100]}",
                ),
                computation=f"LLM extraction: \"{item.get('exact_quote', '')}\"",
                note="; ".join(note_parts),
            )
            logger.info(
                "Extracted %s = %s%s for %s (confidence: %s)",
                kpi_id, value, kpi_def.unit, ticker, confidence,
            )

    return quant_output
