"""
Qualitative engine — LLM-powered filing analysis with mandatory citations.

Provides:
  1. Evidence builder: supporting + disconfirming evidence for user's claims
  2. Red flag detector: sector-aware, every flag cited
  3. Targeted filing query: find exact language in a filing
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import anthropic

from app.config import settings
from app.data import (
    DataResult,
    SourceMeta,
    get_company_filings,
    get_filing_text,
)
from app.prompts import (
    CITATION_RULES,
    EVIDENCE_BUILDER_PROMPT,
    FILING_QUERY_PROMPT,
    RED_FLAG_PROMPT,
    SECTOR_RED_FLAG_CHECKLISTS,
)
from app.templates import SectorTemplate

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-5-20250929"
MAX_FILING_CHARS = 80_000  # Truncate filing text sent to the LLM


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class EvidencePiece:
    content: str
    section: str
    page: int | None
    page_unverified: bool
    content_type: str  # "fact" or "interpretation"


@dataclass
class ClaimEvidence:
    claim_id: str
    supporting: list[EvidencePiece]
    disconfirming: list[EvidencePiece]
    evidence_strength: str  # "strong", "moderate", "weak", "none"
    summary: str
    source: SourceMeta


@dataclass
class RedFlag:
    flag: str
    severity: str  # "high", "medium", "low"
    section: str
    page: int | None
    page_unverified: bool
    evidence: str
    context: str
    source: SourceMeta


@dataclass
class RedFlagReport:
    red_flags: list[RedFlag]
    clean_areas: list[str]
    filing_source: SourceMeta


@dataclass
class FilingPassage:
    excerpt: str
    section: str
    page: int | None
    page_unverified: bool
    relevance: str
    source: SourceMeta


@dataclass
class FilingQueryResult:
    passages: list[FilingPassage]
    query_answered: bool
    filing_source: SourceMeta


# ---------------------------------------------------------------------------
# QualitativeEngine
# ---------------------------------------------------------------------------

class QualitativeEngine:
    """
    LLM-powered SEC filing analysis. Every output is cited.

    Usage:
        engine = QualitativeEngine()
        evidence = await engine.build_evidence_for_claims("AAPL", claims, "10-K", accession, cik)
    """

    def __init__(self) -> None:
        if not settings.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required for the qualitative engine. "
                "Set it in .env."
            )
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    # -------------------------------------------------------------------
    # Evidence builder
    # -------------------------------------------------------------------

    async def build_evidence_for_claims(
        self,
        ticker: str,
        claims: list[dict],
        form_type: str,
        accession_number: str,
        cik: str,
    ) -> list[ClaimEvidence]:
        """
        Given user's claims, search a filing for supporting and disconfirming
        evidence. Every output is cited with section name.

        Args:
            claims: list of {"id": "ASML-C1", "statement": "...", "kpi": "..."}
        """
        filing_result = await get_filing_text(accession_number, cik)
        filing_text = filing_result.data[:MAX_FILING_CHARS]
        filing_source = filing_result.source

        if not filing_text:
            logger.warning("Empty filing text for %s", accession_number)
            return []

        # Find the filing date from the accession
        filing_date = filing_source.filing_date or "unknown"

        prompt = EVIDENCE_BUILDER_PROMPT.format(
            citation_rules=CITATION_RULES,
            ticker=ticker,
            form_type=form_type,
            filing_date=filing_date,
            accession_number=accession_number,
            claims_json=json.dumps(claims, indent=2),
            filing_text=filing_text,
        )

        response = await self.client.messages.create(
            model=MODEL,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = self._extract_json(response.content[0].text)
        if raw is None:
            logger.warning("Failed to parse evidence response as JSON")
            return []

        results: list[ClaimEvidence] = []
        for item in raw.get("claim_evidence", []):
            results.append(ClaimEvidence(
                claim_id=item.get("claim_id", ""),
                supporting=[
                    EvidencePiece(
                        content=e.get("content", ""),
                        section=e.get("section", ""),
                        page=e.get("page"),
                        page_unverified=e.get("page_unverified", True),
                        content_type=e.get("type", "fact"),
                    )
                    for e in item.get("supporting", [])
                ],
                disconfirming=[
                    EvidencePiece(
                        content=e.get("content", ""),
                        section=e.get("section", ""),
                        page=e.get("page"),
                        page_unverified=e.get("page_unverified", True),
                        content_type=e.get("type", "fact"),
                    )
                    for e in item.get("disconfirming", [])
                ],
                evidence_strength=item.get("evidence_strength", "none"),
                summary=item.get("summary", ""),
                source=filing_source,
            ))

        return results

    # -------------------------------------------------------------------
    # Red flag detector
    # -------------------------------------------------------------------

    async def detect_red_flags(
        self,
        ticker: str,
        template: SectorTemplate,
        form_type: str,
        accession_number: str,
        cik: str,
    ) -> RedFlagReport:
        """
        Sector-aware red flag detection on a filing.
        Every flag is cited with filing section.
        """
        filing_result = await get_filing_text(accession_number, cik)
        filing_text = filing_result.data[:MAX_FILING_CHARS]
        filing_source = filing_result.source

        if not filing_text:
            return RedFlagReport(
                red_flags=[], clean_areas=[], filing_source=filing_source,
            )

        sector_checklist = SECTOR_RED_FLAG_CHECKLISTS.get(
            template.sector,
            "No sector-specific checklist available. Apply universal checks only.",
        )
        filing_date = filing_source.filing_date or "unknown"

        prompt = RED_FLAG_PROMPT.format(
            citation_rules=CITATION_RULES,
            sector_name=template.display_name,
            sector_checklist=sector_checklist,
            ticker=ticker,
            form_type=form_type,
            filing_date=filing_date,
            filing_text=filing_text,
        )

        response = await self.client.messages.create(
            model=MODEL,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = self._extract_json(response.content[0].text)
        if raw is None:
            logger.warning("Failed to parse red flag response as JSON")
            return RedFlagReport(
                red_flags=[], clean_areas=[], filing_source=filing_source,
            )

        flags = [
            RedFlag(
                flag=f.get("flag", ""),
                severity=f.get("severity", "low"),
                section=f.get("section", ""),
                page=f.get("page"),
                page_unverified=f.get("page_unverified", True),
                evidence=f.get("evidence", ""),
                context=f.get("context", ""),
                source=filing_source,
            )
            for f in raw.get("red_flags", [])
        ]

        return RedFlagReport(
            red_flags=flags,
            clean_areas=raw.get("clean_areas", []),
            filing_source=filing_source,
        )

    # -------------------------------------------------------------------
    # Targeted filing query
    # -------------------------------------------------------------------

    async def targeted_filing_query(
        self,
        ticker: str,
        query: str,
        form_type: str,
        accession_number: str,
        cik: str,
    ) -> FilingQueryResult:
        """
        Find exact language in a filing that addresses a user query.
        Returns cited excerpts.
        """
        filing_result = await get_filing_text(accession_number, cik)
        filing_text = filing_result.data[:MAX_FILING_CHARS]
        filing_source = filing_result.source

        if not filing_text:
            return FilingQueryResult(
                passages=[], query_answered=False, filing_source=filing_source,
            )

        filing_date = filing_source.filing_date or "unknown"

        prompt = FILING_QUERY_PROMPT.format(
            citation_rules=CITATION_RULES,
            ticker=ticker,
            form_type=form_type,
            filing_date=filing_date,
            query=query,
            filing_text=filing_text,
        )

        response = await self.client.messages.create(
            model=MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = self._extract_json(response.content[0].text)
        if raw is None:
            logger.warning("Failed to parse filing query response as JSON")
            return FilingQueryResult(
                passages=[], query_answered=False, filing_source=filing_source,
            )

        passages = [
            FilingPassage(
                excerpt=p.get("excerpt", ""),
                section=p.get("section", ""),
                page=p.get("page"),
                page_unverified=p.get("page_unverified", True),
                relevance=p.get("relevance", ""),
                source=filing_source,
            )
            for p in raw.get("passages", [])
        ]

        return FilingQueryResult(
            passages=passages,
            query_answered=raw.get("query_answered", len(passages) > 0),
            filing_source=filing_source,
        )

    # -------------------------------------------------------------------
    # Convenience: fetch latest filing and analyze
    # -------------------------------------------------------------------

    async def analyze_latest_filing(
        self,
        ticker: str,
        template: SectorTemplate,
        claims: list[dict],
        form_types: list[str] | None = None,
    ) -> dict:
        """
        Convenience method: fetch the latest filing for a ticker,
        then run evidence building and red flag detection.

        Returns {"evidence": [...], "red_flags": RedFlagReport, "filing": {...}}.
        """
        if form_types is None:
            form_types = ["10-K"]

        filings_result = await get_company_filings(ticker, form_types=form_types, limit=1)
        if not filings_result.data:
            raise ValueError(f"No {form_types} filings found for {ticker}")

        filing = filings_result.data[0]
        form_type = filing["form_type"]
        accession = filing["accession_number"]
        cik = filing["cik"]

        evidence = await self.build_evidence_for_claims(
            ticker, claims, form_type, accession, cik,
        )
        red_flags = await self.detect_red_flags(
            ticker, template, form_type, accession, cik,
        )

        return {
            "evidence": evidence,
            "red_flags": red_flags,
            "filing": filing,
        }

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        """Extract JSON from LLM response, handling markdown fences."""
        text = text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json or ```) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            return None
