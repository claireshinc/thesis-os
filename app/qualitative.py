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
import re
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
    STRUCTURED_KPI_EXTRACTION_PROMPT,
)
from app.templates import SectorTemplate

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-5-20250929"
MAX_FILING_CHARS = 80_000  # Truncate filing text sent to the LLM
MAX_EXTRACTION_CHARS = 40_000  # Shorter context for targeted KPI extraction


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
# Red flag self-contradiction validator
# ---------------------------------------------------------------------------

# Patterns: "X growing faster than Y", "X outpacing Y", "X exceeding Y"
_FASTER_PATTERNS = [
    re.compile(r"(?P<a>[\w\s&/]+?)\s+(?:growing|grew|increasing|increased)\s+(?:faster|more quickly)\s+than\s+(?P<b>[\w\s&/]+)", re.IGNORECASE),
    re.compile(r"(?P<a>[\w\s&/]+?)\s+(?:outpacing|outpaced|outstripping|outstripped)\s+(?P<b>[\w\s&/]+)", re.IGNORECASE),
    re.compile(r"(?P<a>[\w\s&/]+?)\s+(?:exceeding|exceeded|exceeds)\s+(?P<b>[\w\s&/]+?)\s+growth", re.IGNORECASE),
]

# Extract percentage values from evidence text: e.g. "SBC grew 12.3% vs revenue growth of 15.1%"
_PCT_PATTERN = re.compile(r"(-?\d+\.?\d*)\s*%")


def _validate_red_flags(
    flags: list[RedFlag],
    clean_areas: list[str],
) -> tuple[list[RedFlag], list[str]]:
    """
    Post-process LLM red flags to catch self-contradictions.

    If a flag's headline claims "A growing faster than B" but the evidence
    numbers show A's growth rate < B's growth rate, drop the flag and
    reclassify it as a clean area.
    """
    validated: list[RedFlag] = []
    added_clean: list[str] = []

    for flag in flags:
        contradiction = _check_growth_contradiction(flag)
        if contradiction:
            logger.info(
                "Dropping self-contradicting red flag: '%s' — %s",
                flag.flag, contradiction,
            )
            added_clean.append(
                f"{flag.flag} (dropped: evidence contradicts headline — {contradiction})"
            )
        else:
            validated.append(flag)

    return validated, clean_areas + added_clean


def _check_growth_contradiction(flag: RedFlag) -> str | None:
    """
    Check if a flag's evidence contradicts its headline.

    Returns a human-readable reason string if contradicted, None otherwise.
    """
    headline = flag.flag
    evidence = flag.evidence

    # Check for "A growing faster than B" patterns in headline
    for pattern in _FASTER_PATTERNS:
        m = pattern.search(headline)
        if not m:
            continue

        a_name = m.group("a").strip()
        b_name = m.group("b").strip()

        # Extract percentages from evidence
        pcts = _PCT_PATTERN.findall(evidence)
        if len(pcts) < 2:
            return None  # Can't verify without at least 2 numbers

        # Heuristic: the first percentage in evidence relates to 'a',
        # the second relates to 'b'. If a < b, it's a contradiction.
        a_rate = float(pcts[0])
        b_rate = float(pcts[1])

        if a_rate < b_rate:
            return (
                f"{a_name.strip()} growth ({a_rate}%) is actually lower than "
                f"{b_name.strip()} growth ({b_rate}%)"
            )

    return None


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

        # Post-process: drop flags whose evidence contradicts their headline
        flags, clean_areas = _validate_red_flags(
            flags, raw.get("clean_areas", []),
        )

        return RedFlagReport(
            red_flags=flags,
            clean_areas=clean_areas,
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
    # Structured KPI extraction
    # -------------------------------------------------------------------

    async def extract_structured_kpis(
        self,
        ticker: str,
        kpi_requests: list[dict],
        form_type: str,
        accession_number: str,
        cik: str,
    ) -> list[dict]:
        """
        Extract specific KPI values from a filing using targeted LLM analysis.

        Args:
            kpi_requests: list of {"kpi_id": str, "label": str, "hint": str}
                Only KPIs that returned None from XBRL should be passed here.

        Returns:
            list of {"kpi_id", "value", "unit", "period", "section",
                     "confidence", "exact_quote", "note"}
        """
        if not kpi_requests:
            return []

        filing_result = await get_filing_text(accession_number, cik)
        filing_text = filing_result.data[:MAX_EXTRACTION_CHARS]

        if not filing_text:
            logger.warning("Empty filing text for extraction: %s", accession_number)
            return []

        filing_date = filing_result.source.filing_date or "unknown"

        # Format KPI requests for the prompt
        kpi_lines = []
        for req in kpi_requests:
            kpi_lines.append(
                f"- {req['kpi_id']} ({req['label']}): {req['hint']}"
            )

        prompt = STRUCTURED_KPI_EXTRACTION_PROMPT.format(
            ticker=ticker,
            form_type=form_type,
            filing_date=filing_date,
            kpi_requests="\n".join(kpi_lines),
            filing_text=filing_text,
        )

        response = await self.client.messages.create(
            model=MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = self._extract_json(response.content[0].text)
        if raw is None:
            logger.warning("Failed to parse KPI extraction response")
            return []

        return raw.get("extracted_kpis", [])

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
