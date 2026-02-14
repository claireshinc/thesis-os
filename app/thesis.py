"""
Thesis engine — compiler, stress test, and command router.

Provides:
  1. ThesisCompiler: LLM decomposes plain-English thesis into structured claims,
     kill criteria, and catalysts.  Populates KPIs from QuantOutput.
  2. StressTest: adversarial analysis — circular reasoning, priced-in check,
     falsification tests, missing disconfirming evidence, PM questions.
  3. CommandRouter: dispatches /thesis, /stress, /filing, /evidence, /brief
     commands to appropriate engines.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import anthropic

from app.brief import DecisionBriefResponse, generate_brief
from app.config import settings
from app.data import (
    SourceMeta,
    get_company_filings,
    get_company_submissions,
    get_filing_text,
)
from app.flow import FlowEngine, FlowOutput
from app.qualitative import (
    ClaimEvidence,
    FilingQueryResult,
    QualitativeEngine,
    RedFlagReport,
)
from app.quant import QuantEngine, QuantOutput
from app.templates import SECTOR_TEMPLATES, SectorTemplate, get_template

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-5-20250929"


# ═══════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class CompiledClaim:
    id: str  # e.g. "AAPL-C1"
    statement: str
    kpi_id: str
    current_value: float | None
    unit: str
    period: str
    source_guidance: str  # where to find evidence
    yoy_delta: float | None = None
    qoq_delta: float | None = None
    status: str = "supported"  # "supported", "unverified"


@dataclass
class CompiledKillCriterion:
    id: str  # e.g. "AAPL-KC1"
    description: str
    metric: str
    operator: str
    threshold: float
    duration: str
    current_value: float | None
    status: str  # "ok", "watch", "breach"
    distance_pct: float | None
    watch_reason: str | None = None


@dataclass
class CompiledCatalyst:
    event: str
    expected_date: str  # "Q2 2025", "2025-03-15", "next earnings"
    claims_tested: list[str]  # claim IDs
    kill_criteria_tested: list[str]  # kill criterion IDs


@dataclass
class ThesisDraft:
    ticker: str
    direction: str  # "long" or "short"
    thesis_text: str
    sector: str
    sector_display_name: str
    claims: list[CompiledClaim]
    kill_criteria: list[CompiledKillCriterion]
    catalysts: list[CompiledCatalyst]
    generated_at: str


@dataclass
class StressTestResult:
    ticker: str
    thesis_summary: str
    circular_reasoning: list[str]
    already_priced_in: str
    falsification_tests: list[dict]  # {test, how_to_check, current_evidence}
    missing_disconfirming: list[str]
    pm_questions: list[dict]  # {question, why_it_matters}
    generated_at: str


# ═══════════════════════════════════════════════════════════════════════════
# LLM prompts
# ═══════════════════════════════════════════════════════════════════════════

THESIS_COMPILER_PROMPT = """You are a senior research analyst helping a PM structure an investment thesis.

The PM has given you:
- Ticker: {ticker}
- Direction: {direction}
- Thesis: "{thesis_text}"
- Sector template: {sector_name}
- Today's date: {today}

Available KPIs from the quant engine (with current values):
{kpi_summary}

Market-implied context (what the market is currently pricing in):
{market_implied_summary}

Sector kill criteria templates:
{kill_criteria_summary}

Your job: Decompose this thesis into 2-4 specific, falsifiable claims.
Each claim MUST be tied to a measurable KPI.

Respond in JSON (no markdown fences):
{{
  "claims": [
    {{
      "id": "{ticker}-C1",
      "statement": "Specific, falsifiable claim",
      "kpi_id": "the_kpi_id_from_template",
      "source_guidance": "Where to find evidence (e.g., '10-K revenue discussion', 'earnings call transcript')"
    }}
  ],
  "kill_criteria": [
    {{
      "id": "{ticker}-KC1",
      "description": "Human-readable kill criterion",
      "metric": "kpi_id",
      "operator": "<",
      "threshold": 100,
      "duration": "2Q"
    }}
  ],
  "catalysts": [
    {{
      "event": "Q2 2025 earnings release",
      "expected_date": "2025-07-15",
      "claims_tested": ["{ticker}-C1"],
      "kill_criteria_tested": ["{ticker}-KC1"]
    }}
  ]
}}

Rules:
- Claims must be falsifiable — a future data point could prove them wrong.
- Each claim must reference a KPI that can be tracked.
- Kill criteria define when the thesis is dead. Be specific: metric, operator, threshold, duration.
- Propose 1-3 catalysts that will test the thesis (earnings, product launches, regulatory events).
- If the thesis is "long", kill criteria should flag deterioration.
- If the thesis is "short", kill criteria should flag improvement (i.e., the short thesis breaking).
- Do NOT invent KPIs — only use the ones listed above or standard financial metrics.
- Consider the market-implied growth rate. If the market already prices in {implied_growth} growth,
  your claims should articulate WHY growth will differ from what's priced. Kill criteria should
  trigger if the thesis converges with consensus rather than diverging as expected.
""".strip()


STRESS_TEST_PROMPT = """You are an adversarial PM reviewing an investment thesis. Your job is to
find weaknesses, NOT to support the thesis. Be intellectually honest but rigorous.

Ticker: {ticker}
Direction: {direction}
Thesis: "{thesis_text}"

Claims:
{claims_json}

Market data:
- Implied growth rate (from reverse DCF): {implied_growth}
- WACC: {wacc}
- EV: {ev}

Insider activity summary: {insider_summary}
Holder map: {holder_summary}

Respond in JSON (no markdown fences):
{{
  "circular_reasoning": [
    "Any circular logic found in the claims (e.g., 'revenue will grow because the stock is cheap')"
  ],
  "already_priced_in": "What the market is already pricing in based on the reverse DCF implied growth rate, and whether the thesis offers genuine edge vs consensus",
  "falsification_tests": [
    {{
      "test": "What would prove this claim wrong",
      "how_to_check": "Specific data source or filing section to monitor",
      "current_evidence": "What current data says about this test"
    }}
  ],
  "missing_disconfirming": [
    "Evidence the analyst should have looked for but didn't"
  ],
  "pm_questions": [
    {{
      "question": "The single toughest question a PM would ask",
      "why_it_matters": "Why this question cuts to the core of the thesis"
    }}
  ]
}}

Rules:
- Be specific. Reference actual numbers from the data provided.
- "Already priced in" should compare the thesis growth assumptions to the reverse DCF implied growth.
- Falsification tests should be concrete: "If X drops below Y in the next 2 quarters, the thesis is wrong."
- Missing disconfirming evidence: what risks has the analyst NOT considered?
- PM questions: imagine the toughest questions from a skeptical IC member.
- Do NOT recommend buy/sell. Focus on thesis quality, not direction.
""".strip()


# ═══════════════════════════════════════════════════════════════════════════
# ThesisCompiler
# ═══════════════════════════════════════════════════════════════════════════


class ThesisCompiler:
    """
    Decomposes a plain-English thesis into structured claims, kill criteria,
    and catalysts.  Populates current KPI values from QuantOutput.

    Usage:
        compiler = ThesisCompiler()
        draft = await compiler.compile("AAPL", "long", "Apple's services...", quant_output, template)
    """

    def __init__(self) -> None:
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for the thesis compiler.")
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def compile(
        self,
        ticker: str,
        direction: str,
        thesis_text: str,
        quant_output: QuantOutput,
        template: SectorTemplate,
    ) -> ThesisDraft:
        """Compile a thesis into structured claims + kill criteria."""
        ticker = ticker.upper()

        # Build KPI summary for the prompt
        kpi_lines = []
        for kpi_id, kpi_result in quant_output.sector_kpis.items():
            val_str = f"{kpi_result.value}{kpi_result.unit}" if kpi_result.value is not None else "N/A"
            yoy = f", YoY delta: {kpi_result.yoy_delta}" if kpi_result.yoy_delta is not None else ""
            qoq = f", QoQ delta: {kpi_result.qoq_delta}" if kpi_result.qoq_delta is not None else ""
            note = f" ({kpi_result.note})" if kpi_result.note else ""
            kpi_lines.append(
                f"- {kpi_result.label} ({kpi_id}): {val_str} [{kpi_result.period}]{yoy}{qoq}{note}"
            )
        kpi_summary = "\n".join(kpi_lines) if kpi_lines else "No KPIs computed yet."

        # Build kill criteria summary from template defaults
        kc_lines = []
        for kc in template.default_kill_criteria:
            kc_lines.append(f"- {kc.description} (metric: {kc.metric}, {kc.operator} {kc.threshold}, duration: {kc.duration})")
        kill_criteria_summary = "\n".join(kc_lines) if kc_lines else "No default kill criteria."

        # Build market-implied summary for the prompt
        mi = quant_output.market_implied
        if mi:
            ig = mi.implied_fcf_growth_10yr
            implied_growth = (
                f"{ig:.1%}"
                if ig is not None and ig == ig  # NaN check
                else "no solution (market price may not support a standard DCF)"
            )
            ev_str = f"${quant_output.ev_build.enterprise_value:,.0f}"
            market_implied_summary = (
                f"- Reverse DCF implied FCF growth (10yr): {implied_growth}\n"
                f"- WACC: {mi.wacc:.2%} ({mi.wacc_build})\n"
                f"- Enterprise value: {ev_str}\n"
                f"- FCF used: ${mi.fcf_used:,.0f}\n"
                f"- Terminal growth assumption: {mi.terminal_growth:.1%}\n"
                f"- Sensitivity: {', '.join(f'{k}: {v:.1%}' if v is not None and v == v else f'{k}: N/A' for k, v in mi.sensitivity.items())}"
            )
        else:
            market_implied_summary = "Not available (no market price data)."
            implied_growth = "N/A"

        prompt = THESIS_COMPILER_PROMPT.format(
            ticker=ticker,
            direction=direction,
            thesis_text=thesis_text,
            sector_name=template.display_name,
            today=date.today().isoformat(),
            kpi_summary=kpi_summary,
            market_implied_summary=market_implied_summary,
            implied_growth=implied_growth,
            kill_criteria_summary=kill_criteria_summary,
        )

        response = await self.client.messages.create(
            model=MODEL,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = _extract_json(response.content[0].text)
        if raw is None:
            logger.warning("Failed to parse thesis compiler response as JSON")
            return ThesisDraft(
                ticker=ticker, direction=direction, thesis_text=thesis_text,
                sector=template.sector, sector_display_name=template.display_name,
                claims=[], kill_criteria=[], catalysts=[],
                generated_at=datetime.utcnow().isoformat() + "Z",
            )

        # Build claims with current KPI values
        claims = []
        for c in raw.get("claims", []):
            kpi_id = c.get("kpi_id", "")
            kpi_data = quant_output.sector_kpis.get(kpi_id)
            claims.append(CompiledClaim(
                id=c.get("id", ""),
                statement=c.get("statement", ""),
                kpi_id=kpi_id,
                current_value=kpi_data.value if kpi_data else None,
                unit=kpi_data.unit if kpi_data else "",
                period=kpi_data.period if kpi_data else "?",
                source_guidance=c.get("source_guidance", ""),
                yoy_delta=kpi_data.yoy_delta if kpi_data else None,
                qoq_delta=kpi_data.qoq_delta if kpi_data else None,
            ))

        # Build kill criteria with current values + status
        kill_criteria = []
        for kc in raw.get("kill_criteria", []):
            metric = kc.get("metric", "")
            kpi_data = quant_output.sector_kpis.get(metric)
            current_val = kpi_data.value if kpi_data else None
            threshold = kc.get("threshold", 0)
            operator = kc.get("operator", "<")

            status, distance = _evaluate_kill_criterion(
                current_val, threshold, operator,
            )

            kill_criteria.append(CompiledKillCriterion(
                id=kc.get("id", ""),
                description=kc.get("description", ""),
                metric=metric,
                operator=operator,
                threshold=threshold,
                duration=kc.get("duration", ""),
                current_value=current_val,
                status=status,
                distance_pct=distance,
            ))

        # Build catalysts
        catalysts = [
            CompiledCatalyst(
                event=cat.get("event", ""),
                expected_date=cat.get("expected_date", ""),
                claims_tested=cat.get("claims_tested", []),
                kill_criteria_tested=cat.get("kill_criteria_tested", []),
            )
            for cat in raw.get("catalysts", [])
        ]

        # Post-LLM validation pass
        claims, kill_criteria, catalysts = _validate_draft(
            claims, kill_criteria, catalysts, date.today(),
        )

        return ThesisDraft(
            ticker=ticker,
            direction=direction,
            thesis_text=thesis_text,
            sector=template.sector,
            sector_display_name=template.display_name,
            claims=claims,
            kill_criteria=kill_criteria,
            catalysts=catalysts,
            generated_at=datetime.utcnow().isoformat() + "Z",
        )


# ═══════════════════════════════════════════════════════════════════════════
# StressTest
# ═══════════════════════════════════════════════════════════════════════════


class StressTest:
    """
    Adversarial analysis of a thesis.

    Usage:
        stress = StressTest()
        result = await stress.run("AAPL", draft, quant_output, flow_output)
    """

    def __init__(self) -> None:
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for stress tests.")
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def run(
        self,
        ticker: str,
        draft: ThesisDraft,
        quant_output: QuantOutput,
        flow_output: FlowOutput,
    ) -> StressTestResult:
        """Run adversarial stress test on a thesis draft."""
        ticker = ticker.upper()

        # Prepare claim data for the prompt
        claims_for_prompt = [
            {
                "id": c.id,
                "statement": c.statement,
                "kpi": c.kpi_id,
                "current_value": c.current_value,
                "unit": c.unit,
                "yoy_delta": c.yoy_delta,
                "qoq_delta": c.qoq_delta,
            }
            for c in draft.claims
        ]

        # Market implied data
        mi = quant_output.market_implied
        implied_growth = (
            f"{mi.implied_fcf_growth_10yr:.1%}" if mi and mi.implied_fcf_growth_10yr == mi.implied_fcf_growth_10yr  # NaN check
            else "unavailable (no market price)"
        )
        wacc = f"{mi.wacc:.2%}" if mi else "unavailable"
        ev = f"${quant_output.ev_build.enterprise_value:,.0f}" if quant_output.ev_build else "unavailable"

        # Insider + holder summary
        hm = flow_output.holder_map
        insider_summary = hm.insider_summary
        holder_types = {}
        for h in hm.top_holders:
            holder_types[h.fund_type] = holder_types.get(h.fund_type, 0) + 1
        holder_data_note = getattr(hm, "holder_data_note", "")
        holder_summary = (
            f"{hm.holder_count} institutional holders "
            f"({', '.join(f'{v} {k}' for k, v in holder_types.items())})"
        )
        if holder_data_note:
            holder_summary += f" NOTE: {holder_data_note}"

        prompt = STRESS_TEST_PROMPT.format(
            ticker=ticker,
            direction=draft.direction,
            thesis_text=draft.thesis_text,
            claims_json=json.dumps(claims_for_prompt, indent=2),
            implied_growth=implied_growth,
            wacc=wacc,
            ev=ev,
            insider_summary=insider_summary,
            holder_summary=holder_summary,
        )

        response = await self.client.messages.create(
            model=MODEL,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = _extract_json(response.content[0].text)
        if raw is None:
            logger.warning("Failed to parse stress test response as JSON")
            return StressTestResult(
                ticker=ticker, thesis_summary=draft.thesis_text,
                circular_reasoning=[], already_priced_in="Analysis failed",
                falsification_tests=[], missing_disconfirming=[],
                pm_questions=[], generated_at=datetime.utcnow().isoformat() + "Z",
            )

        return StressTestResult(
            ticker=ticker,
            thesis_summary=draft.thesis_text,
            circular_reasoning=raw.get("circular_reasoning", []),
            already_priced_in=raw.get("already_priced_in", ""),
            falsification_tests=raw.get("falsification_tests", []),
            missing_disconfirming=raw.get("missing_disconfirming", []),
            pm_questions=raw.get("pm_questions", []),
            generated_at=datetime.utcnow().isoformat() + "Z",
        )


# ═══════════════════════════════════════════════════════════════════════════
# CommandRouter
# ═══════════════════════════════════════════════════════════════════════════


class CommandRouter:
    """
    Dispatches user commands to the appropriate engines.

    Supported commands:
        /thesis <TICKER> <long|short> — <thesis text>
        /stress <TICKER> — <memo text or paste bullets>
        /filing <TICKER> <query>
        /evidence <TICKER> <claim_id>
        /brief <TICKER>

    Usage:
        router = CommandRouter()
        result = await router.dispatch("/thesis AAPL long — Apple's services...")
    """

    def __init__(self) -> None:
        self._quant = QuantEngine()
        self._flow = FlowEngine()
        self._qual: QualitativeEngine | None = None
        self._compiler: ThesisCompiler | None = None
        self._stress: StressTest | None = None

        if settings.anthropic_api_key:
            self._qual = QualitativeEngine()
            self._compiler = ThesisCompiler()
            self._stress = StressTest()

    async def dispatch(self, command: str) -> dict:
        """
        Parse and dispatch a command string.

        Returns a dict with:
          - "command": the parsed command name
          - "result": the command output (varies by command)
          - "error": error message if command failed (None on success)
        """
        command = command.strip()
        if not command.startswith("/"):
            return {"command": "unknown", "result": None, "error": "Commands must start with /"}

        parts = command.split(None, 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handlers = {
            "/thesis": self._handle_thesis,
            "/stress": self._handle_stress,
            "/filing": self._handle_filing,
            "/evidence": self._handle_evidence,
            "/brief": self._handle_brief,
        }

        handler = handlers.get(cmd)
        if handler is None:
            return {
                "command": cmd,
                "result": None,
                "error": f"Unknown command '{cmd}'. Available: {', '.join(sorted(handlers.keys()))}",
            }

        try:
            result = await handler(args)
            return {"command": cmd, "result": result, "error": None}
        except Exception as exc:
            logger.error("Command %s failed: %s", cmd, exc, exc_info=True)
            return {"command": cmd, "result": None, "error": str(exc)}

    # -------------------------------------------------------------------
    # /thesis <TICKER> <long|short> — <thesis text>
    # -------------------------------------------------------------------

    async def _handle_thesis(self, args: str) -> dict:
        if not self._compiler:
            raise ValueError("ANTHROPIC_API_KEY required for /thesis")

        # Parse: "AAPL long — Apple's services revenue will..."
        if "—" in args:
            header, thesis_text = args.split("—", 1)
        elif "--" in args:
            header, thesis_text = args.split("--", 1)
        elif " - " in args:
            # Only split on " - " (space-dash-space) to avoid splitting on hyphens in words
            header, thesis_text = args.split(" - ", 1)
        else:
            raise ValueError(
                "Format: /thesis <TICKER> <long|short> — <thesis text>"
            )

        header_parts = header.strip().split()
        if len(header_parts) < 2:
            raise ValueError("Format: /thesis <TICKER> <long|short> — <thesis text>")

        ticker = header_parts[0].upper()
        direction = header_parts[1].lower()
        thesis_text = thesis_text.strip()

        if direction not in ("long", "short"):
            raise ValueError(f"Direction must be 'long' or 'short', got '{direction}'")

        # Detect sector + run quant for current KPI values
        import asyncio
        from app.brief import detect_sector

        sector_key, template, sub_meta = await detect_sector(ticker)
        quant_output = await self._quant.analyze(ticker, template)

        # Compile thesis
        draft = await self._compiler.compile(
            ticker, direction, thesis_text, quant_output, template,
        )

        return _draft_to_dict(draft)

    # -------------------------------------------------------------------
    # /stress <TICKER> — <memo text>
    # -------------------------------------------------------------------

    async def _handle_stress(self, args: str) -> dict:
        if not self._stress:
            raise ValueError("ANTHROPIC_API_KEY required for /stress")

        if "—" in args:
            ticker, memo = args.split("—", 1)
        elif "--" in args:
            ticker, memo = args.split("--", 1)
        elif " - " in args:
            ticker, memo = args.split(" - ", 1)
        else:
            raise ValueError("Format: /stress <TICKER> — <memo text or bullets>")

        ticker = ticker.strip().upper()
        memo = memo.strip()

        import asyncio
        from app.brief import detect_sector

        sector_key, template, _ = await detect_sector(ticker)

        # Run quant + flow in parallel for stress test context
        quant_task = self._quant.analyze(ticker, template)
        flow_task = self._flow.analyze(ticker)
        quant_output, flow_output = await asyncio.gather(quant_task, flow_task)

        # Build a minimal draft from memo for the stress test
        draft = ThesisDraft(
            ticker=ticker,
            direction="long",  # stress test works for either direction
            thesis_text=memo,
            sector=template.sector,
            sector_display_name=template.display_name,
            claims=[],
            kill_criteria=[],
            catalysts=[],
            generated_at=datetime.utcnow().isoformat() + "Z",
        )

        result = await self._stress.run(ticker, draft, quant_output, flow_output)
        return _stress_to_dict(result)

    # -------------------------------------------------------------------
    # /filing <TICKER> <query>
    # -------------------------------------------------------------------

    async def _handle_filing(self, args: str) -> dict:
        if not self._qual:
            raise ValueError("ANTHROPIC_API_KEY required for /filing")

        parts = args.strip().split(None, 1)
        if len(parts) < 2:
            raise ValueError("Format: /filing <TICKER> <query>")

        ticker = parts[0].upper()
        query = parts[1]

        # Fetch latest 10-K
        filings = await get_company_filings(ticker, form_types=["10-K", "10-K/A"], limit=1)
        if not filings.data:
            raise ValueError(f"No 10-K filings found for {ticker}")

        filing = filings.data[0]
        result = await self._qual.targeted_filing_query(
            ticker, query, filing["form_type"],
            filing["accession_number"], filing["cik"],
        )

        return {
            "ticker": ticker,
            "query": query,
            "filing": f"{filing['form_type']} ({filing['filing_date']})",
            "query_answered": result.query_answered,
            "passages": [
                {
                    "excerpt": p.excerpt,
                    "section": p.section,
                    "page": p.page,
                    "page_unverified": p.page_unverified,
                    "relevance": p.relevance,
                }
                for p in result.passages
            ],
        }

    # -------------------------------------------------------------------
    # /evidence <TICKER> <claim_statement_or_id>
    # -------------------------------------------------------------------

    async def _handle_evidence(self, args: str) -> dict:
        if not self._qual:
            raise ValueError("ANTHROPIC_API_KEY required for /evidence")

        parts = args.strip().split(None, 1)
        if len(parts) < 2:
            raise ValueError("Format: /evidence <TICKER> <claim statement>")

        ticker = parts[0].upper()
        claim_text = parts[1]

        # Fetch latest 10-K
        filings = await get_company_filings(ticker, form_types=["10-K", "10-K/A"], limit=1)
        if not filings.data:
            raise ValueError(f"No 10-K filings found for {ticker}")

        filing = filings.data[0]
        claims = [{"id": f"{ticker}-Q1", "statement": claim_text, "kpi": ""}]

        evidence = await self._qual.build_evidence_for_claims(
            ticker, claims, filing["form_type"],
            filing["accession_number"], filing["cik"],
        )

        results = []
        for ev in evidence:
            results.append({
                "claim_id": ev.claim_id,
                "evidence_strength": ev.evidence_strength,
                "summary": ev.summary,
                "supporting": [
                    {"content": e.content, "section": e.section, "type": e.content_type}
                    for e in ev.supporting
                ],
                "disconfirming": [
                    {"content": e.content, "section": e.section, "type": e.content_type}
                    for e in ev.disconfirming
                ],
            })

        return {
            "ticker": ticker,
            "claim": claim_text,
            "filing": f"{filing['form_type']} ({filing['filing_date']})",
            "evidence": results,
        }

    # -------------------------------------------------------------------
    # /brief <TICKER>
    # -------------------------------------------------------------------

    async def _handle_brief(self, args: str) -> dict:
        ticker = args.strip().split()[0].upper() if args.strip() else ""
        if not ticker:
            raise ValueError("Format: /brief <TICKER>")

        brief = await generate_brief(ticker)
        return brief.model_dump()


# ═══════════════════════════════════════════════════════════════════════════
# Kill criterion evaluation
# ═══════════════════════════════════════════════════════════════════════════


def _evaluate_kill_criterion(
    current_value: float | None,
    threshold: float,
    operator: str,
) -> tuple[str, float | None]:
    """
    Evaluate a kill criterion against the current value.

    Returns (status, distance_pct) where:
      - status: "ok", "watch" (within 20% of threshold), or "breach"
      - distance_pct: percentage distance from threshold (positive = safe)
    """
    if current_value is None:
        return "ok", None

    if threshold == 0:
        distance = current_value  # avoid division by zero
        distance_pct = None
    else:
        distance_pct = abs(current_value - threshold) / abs(threshold) * 100

    # Check breach
    if operator in ("<", "<="):
        if current_value < threshold:
            return "breach", 0.0
        if distance_pct is not None and distance_pct < 20:
            return "watch", round(distance_pct, 1)
        return "ok", round(distance_pct, 1) if distance_pct is not None else None

    if operator in (">", ">="):
        if current_value > threshold:
            return "breach", 0.0
        if distance_pct is not None and distance_pct < 20:
            return "watch", round(distance_pct, 1)
        return "ok", round(distance_pct, 1) if distance_pct is not None else None

    # Complex operators (e.g., "qoq_decline >") — default to ok
    return "ok", distance_pct


# ═══════════════════════════════════════════════════════════════════════════
# Post-LLM validation
# ═══════════════════════════════════════════════════════════════════════════

# Trend words that assert a directional movement
_TREND_UP = {"growing", "rising", "increasing", "expanding", "accelerating", "inflects", "improves"}
_TREND_DOWN = {"declining", "falling", "decreasing", "shrinking", "compressing", "contracting", "deteriorating"}


def _validate_draft(
    claims: list[CompiledClaim],
    kill_criteria: list[CompiledKillCriterion],
    catalysts: list[CompiledCatalyst],
    today: date,
) -> tuple[list[CompiledClaim], list[CompiledKillCriterion], list[CompiledCatalyst]]:
    """
    Post-LLM validation pass:
      (a) Drop catalysts with event_date before today
      (b) Set status='no_data' for kill criteria with null current_value
      (c) Flag claims with unsupported trend assertions as 'unverified'
    """
    # (a) Filter out past catalysts
    valid_catalysts = []
    for cat in catalysts:
        cat_date = _parse_catalyst_date_safe(cat.expected_date)
        if cat_date is not None and cat_date < today:
            logger.info(
                "Dropping past catalyst: '%s' (date: %s, today: %s)",
                cat.event, cat.expected_date, today,
            )
            continue
        valid_catalysts.append(cat)

    # (b) Kill criteria with no data
    for kc in kill_criteria:
        if kc.current_value is None:
            kc.status = "no_data"
            kc.distance_pct = None

    # (c) Check trend assertions in claims against actual deltas
    for claim in claims:
        statement_lower = claim.statement.lower()
        words = set(statement_lower.split())

        # Check for upward trend assertion
        if words & _TREND_UP:
            if claim.qoq_delta is not None and claim.qoq_delta < 0:
                claim.status = "unverified"
            elif claim.yoy_delta is not None and claim.yoy_delta < 0:
                claim.status = "unverified"

        # Check for downward trend assertion
        if words & _TREND_DOWN:
            if claim.qoq_delta is not None and claim.qoq_delta > 0:
                claim.status = "unverified"
            elif claim.yoy_delta is not None and claim.yoy_delta > 0:
                claim.status = "unverified"

    return claims, kill_criteria, valid_catalysts


def _parse_catalyst_date_safe(date_str: str) -> date | None:
    """Best-effort parse of a catalyst date string. Returns None if unparseable."""
    # ISO format
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        pass

    # "Q2 2025" → approximate to quarter-end
    upper = (date_str or "").upper().strip()
    if upper.startswith("Q") and len(upper) >= 6:
        try:
            q = int(upper[1])
            year = int(upper.split()[-1])
            month = q * 3
            return date(year, month, 28)
        except (ValueError, IndexError):
            pass

    return None


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _extract_json(text: str) -> dict | None:
    """Extract JSON from LLM response, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return None


def _draft_to_dict(draft: ThesisDraft) -> dict:
    """Convert ThesisDraft to a serializable dict."""
    return {
        "ticker": draft.ticker,
        "direction": draft.direction,
        "thesis_text": draft.thesis_text,
        "sector": draft.sector,
        "sector_display_name": draft.sector_display_name,
        "claims": [
            {
                "id": c.id,
                "statement": c.statement,
                "kpi_id": c.kpi_id,
                "current_value": c.current_value,
                "unit": c.unit,
                "period": c.period,
                "yoy_delta": c.yoy_delta,
                "qoq_delta": c.qoq_delta,
                "source_guidance": c.source_guidance,
            }
            for c in draft.claims
        ],
        "kill_criteria": [
            {
                "id": kc.id,
                "description": kc.description,
                "metric": kc.metric,
                "operator": kc.operator,
                "threshold": kc.threshold,
                "duration": kc.duration,
                "current_value": kc.current_value,
                "status": kc.status,
                "distance_pct": kc.distance_pct,
                "watch_reason": kc.watch_reason,
            }
            for kc in draft.kill_criteria
        ],
        "catalysts": [
            {
                "event": cat.event,
                "expected_date": cat.expected_date,
                "claims_tested": cat.claims_tested,
                "kill_criteria_tested": cat.kill_criteria_tested,
            }
            for cat in draft.catalysts
        ],
        "generated_at": draft.generated_at,
    }


def _stress_to_dict(result: StressTestResult) -> dict:
    """Convert StressTestResult to a serializable dict."""
    return {
        "ticker": result.ticker,
        "thesis_summary": result.thesis_summary,
        "circular_reasoning": result.circular_reasoning,
        "already_priced_in": result.already_priced_in,
        "falsification_tests": result.falsification_tests,
        "missing_disconfirming": result.missing_disconfirming,
        "pm_questions": result.pm_questions,
        "generated_at": result.generated_at,
    }
