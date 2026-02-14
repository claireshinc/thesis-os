# Thesis OS — Revised Architectural Plan

## What Changed and Why

The original plan was a research dashboard. The feedback correctly identifies that PMs don't want dashboards — they want decision artifacts. The product is now restructured around three surfaces that map to how PMs actually work: read a brief, check what changed, build and monitor a thesis. Everything else is subordinate to those three workflows.

Key shifts from v1:

- **Conviction scores are gone.** Replaced with falsifiable claims, kill criteria with thresholds, and "what's priced in" stated plainly. PMs don't outsource judgment. They outsource evidence gathering.
- **Every number is cited.** Source filing, section, date, and the exact computation used. No "LLM said" outputs. Facts and interpretation are visually separated.
- **Industry templates are mandatory.** Generic Piotroski across banks and SaaS creates false signals. Each sector gets its own KPI pack, accounting adjustments, and kill-criteria primitives.
- **Flow is context, not alpha.** 13F becomes "crowding and holder mapping." Insider data gets role/size/plan filters. Options flow is descriptive unless dealer positioning is available.
- **Chat is the controller, not the display.** Chat compiles theses, stress-tests memos, and executes commands. Structured cards are the stable, auditable output.

---

## The Three Surfaces

### Surface 1: Decision Brief (Per Ticker)

A single screen. 90 seconds to read. Exportable to PDF and markdown. This is the primary output — what a PM sees when they pull up a name.

```
┌─────────────────────────────────────────────────────────────────┐
│  DECISION BRIEF: ASML NV                                        │
│  Generated: 2026-02-14 09:30 UTC  │  Sector Template: Semis     │
│  Last filing: 10-K (2025-12-31)   │  Next earnings: 2026-04-16  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  POSITION & VARIANT PERCEPTION                                   │
│  ─────────────────────────────                                   │
│  Your bet: EUV attach rate inflects as TSMC/Samsung move to      │
│  A16/2nm, driving services mix and gross margin expansion.       │
│                                                                  │
│  Market-implied: Reverse DCF prices 14.2% revenue CAGR for      │
│  10yr at 8.1% WACC. Consensus is 16.8%. [source: FCF of         │
│  €4.2B per 2025 10-K p.47; EV build: mkt cap €312B + net        │
│  debt €(4.1B) per p.63; WACC: rf 3.8% + β1.12 × ERP 4.5%]     │
│                                                                  │
│  Edge: The delta is not growth — it's margin mix. Market          │
│  prices 52% gross margin through 2030. If services/installed     │
│  base reaches 30% of revenue (currently 24%), gross margin       │
│  structurally reprices to 55-57%. That's a ~€15-20/share gap    │
│  not captured in top-line consensus.                             │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  CLAIMS TABLE                                                    │
│  ────────────                                                    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ Claim 1: EUV attach rate rises from ~70% to 85%+ at     │    │
│  │          leading-edge nodes by 2028                      │    │
│  │                                                          │    │
│  │ KPI: EUV systems as % of litho revenue                   │    │
│  │ Latest: 72% (Q4 2025) │ QoQ: +1.8pp │ YoY: +6.2pp      │    │
│  │ Source: ASML 10-K 2025, Revenue Disaggregation, p.34     │    │
│  │                                                          │    │
│  │ Supporting: TSMC N2 ramp confirmed (TSMC 10-K p.12);    │    │
│  │   Samsung 2nm GAA timeline reaffirmed (earnings call     │    │
│  │   2025-10-17, mgmt commentary); Intel 18A node           │    │
│  │   restarting EUV orders (8-K 2025-11-02).               │    │
│  │                                                          │    │
│  │ Disconfirming: High-NA EUV adoption slower than          │    │
│  │   expected — only 2 High-NA shipped in 2025 vs guide     │    │
│  │   of 5 (10-K p.38); China DUV workaround patents        │    │
│  │   filed +40% YoY (SIPO database, 2025 filings).         │    │
│  │                                                          │    │
│  │ Catalyst: Q1 2026 earnings (Apr 16) — backlog            │    │
│  │   disclosure tests this directly.                        │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  [Claim 2, 3, 4 in same format...]                              │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  KILL CRITERIA                                                   │
│  ─────────────                                                   │
│  ┌────────────────────────────────────────────────────────┐      │
│  │ 1. Backlog < €35B for 2 consecutive quarters            │     │
│  │    Current: €39.2B (Q4 2025, 10-K p.41)                │      │
│  │    Status: ● OK  │  Distance: 10.7% headroom            │     │
│  │                                                         │      │
│  │ 2. Gross margin < 50% for 2 consecutive quarters        │     │
│  │    Current: 52.4% (Q4 2025, 10-K p.28)                 │      │
│  │    Status: ● WATCH  │  Distance: 2.4pp                  │     │
│  │    Reason: Q3 was 50.8%, near threshold.                │      │
│  │                                                         │      │
│  │ 3. China revenue > 40% of total for any quarter         │     │
│  │    Current: 27% (Q4 2025, geographic segment, p.36)     │      │
│  │    Status: ● OK  │  Distance: 13pp headroom             │     │
│  │                                                         │      │
│  │ 4. Services/installed base revenue growth < 5% YoY      │     │
│  │    Current: +14% YoY (Q4 2025, p.35)                   │      │
│  │    Status: ● OK  │  Distance: 9pp headroom              │     │
│  └────────────────────────────────────────────────────────┘      │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  CATALYST CALENDAR                                               │
│  ─────────────────                                               │
│  Apr 16  Q1 2026 earnings — tests Claim 1 (backlog), Claim 2   │
│  Jun 3   TSMC N2 volume production date — tests Claim 1         │
│  Jul 15  Dutch export control review — tests Kill #3             │
│  Oct 15  Q3 2026 earnings — services mix update for Claim 3     │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  RISK REGISTER                                                   │
│  ──────────────                                                  │
│  1. Export restriction escalation (NL/US/JP alignment)           │
│     Leading indicator: diplomatic statements, ASML China         │
│     order disclosure in quarterly filings                        │
│     Hedge note: Long ASML / short SMIC as partial offset        │
│                                                                  │
│  2. Customer capex cuts (TSMC/Samsung/Intel reduce litho spend) │
│     Leading indicator: customer capex guidance revisions,        │
│     WFE industry forecasts (SEMI.org data)                      │
│     Hedge note: monitor KLAC/LRCX order trends as leading       │
│                                                                  │
│  3. High-NA delays push margin inflection to 2028+              │
│     Leading indicator: High-NA unit shipments per quarter        │
│     Hedge note: if delayed, thesis reprices but doesn't break   │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  HOLDER MAP (context, not signal)                                │
│  ────────────────────────────────                                │
│  Top 5 HF holders: [names, % port, QoQ change]                  │
│  HF concentration: 18% of float (75th percentile vs semis)      │
│  Insider activity (discretionary only): CFO sold €1.2M           │
│    (routine, within 10b5-1 plan parameters, <2% of holdings)    │
│  Short interest: 1.2% of float (low, not a factor)              │
│                                                                  │
│  Source: 13F filings (Q4 2025, 45-day lag), Forms 4 (Jan-Feb    │
│  2026), exchange-reported SI.                                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### Decision Brief Data Model

```python
@dataclass
class DecisionBrief:
    ticker: str
    sector_template: str
    generated_at: datetime
    last_filing: FilingRef          # filing type, date, accession number

    # Position & Variant Perception
    your_bet: str                   # 1 sentence — what must be true
    market_implied: MarketImplied   # reverse DCF output with full source chain
    edge: str                       # the specific delta vs market

    # Claims (2-4)
    claims: list[Claim]

    # Kill Criteria (3-5)
    kill_criteria: list[KillCriterion]

    # Catalyst Calendar
    catalysts: list[Catalyst]

    # Risk Register (top 3)
    risks: list[Risk]

    # Holder Map (context)
    holder_map: HolderMap


@dataclass
class Claim:
    id: str                         # e.g., "ASML-C1"
    statement: str
    kpi: str                        # the metric that tracks this claim
    latest_value: float
    qoq_delta: float
    yoy_delta: float
    source: Citation                # filing, page, section, date
    supporting_evidence: list[Citation]
    disconfirming_evidence: list[Citation]
    catalyst: CatalystRef           # which upcoming event tests this claim
    status: str                     # "supported", "mixed", "challenged"


@dataclass
class KillCriterion:
    id: str
    description: str
    metric: str
    threshold: float
    threshold_duration: str         # e.g., "2 consecutive quarters"
    current_value: float
    current_source: Citation
    status: str                     # "ok", "watch", "breach"
    distance_to_threshold: float    # percentage or absolute
    watch_reason: str | None        # why it moved to watch


@dataclass
class Citation:
    """Every number must trace back to this."""
    source_type: str                # "10-K", "10-Q", "8-K", "earnings_call", "13F", "form4"
    filer: str                      # company or fund name
    filing_date: date
    section: str                    # "Revenue Disaggregation", "MD&A", etc.
    page: int | None
    accession_number: str | None    # SEC EDGAR accession
    url: str                        # direct link to filing
    extracted_text: str | None      # the exact passage, if relevant
    computation: str | None         # e.g., "EV = mkt_cap (€312B) + total_debt (€5.1B) - cash (€9.2B)"


@dataclass
class MarketImplied:
    reverse_dcf_growth: float
    wacc: float
    wacc_build: str                 # "rf 3.8% + β1.12 × ERP 4.5%"
    fcf_used: float
    fcf_source: Citation
    ev_used: float
    ev_build: str                   # "mkt_cap + debt - cash" with numbers
    ev_source: Citation
    consensus_growth: float
    consensus_source: str           # "FactSet consensus as of 2026-02-14"
    margin_assumption: str          # what margin the market prices


@dataclass
class Catalyst:
    date: date
    event: str
    claims_tested: list[str]        # claim IDs
    kill_criteria_tested: list[str] # kill criterion IDs


@dataclass
class Risk:
    description: str
    leading_indicator: str
    data_source: str
    hedge_note: str | None


@dataclass
class HolderMap:
    top_hf_holders: list[HolderEntry]
    hf_concentration: float         # % of float
    hf_concentration_percentile: float  # vs sector
    insider_activity: list[InsiderEntry]
    insider_note: str               # contextual interpretation
    short_interest_pct: float
    short_interest_interpretation: str
    data_lag_note: str              # "13F data is 45 days lagged"


@dataclass
class InsiderEntry:
    name: str
    title: str
    transaction_type: str           # "purchase" or "sale"
    value: float
    date: date
    is_10b5_1: bool                 # plan vs discretionary
    pct_of_holdings: float          # size relative to their total
    source: Citation
```

---

### Surface 2: What Changed Feed

The daily product people actually open. A stream of deltas — like GitHub commits for fundamentals.

```
┌─────────────────────────────────────────────────────────────────┐
│  WHAT CHANGED  │  Portfolio  │  Watchlist  │  All               │
│  Filter: ● Claim-linked  ○ All updates  ○ Kill criteria only   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  TODAY — Feb 14, 2026                                           │
│                                                                  │
│  ┌─ ASML ── 8-K filed ──────────────────────────── 08:15 UTC ─┐│
│  │  What: Customer prepayment of €2.8B received from unnamed   ││
│  │        "major logic customer" (8-K, Exhibit 99.1).          ││
│  │  Why it matters: Confirms continued EUV order momentum.     ││
│  │        Prior quarter prepayment was €1.9B.                  ││
│  │  Claims impacted: Claim 1 (EUV attach) — SUPPORTS          ││
│  │  Kill criteria: None affected.                              ││
│  │  [View filing →]                                            ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─ CRWD ── 13F ownership shift ────────────────── 07:30 UTC ─┐│
│  │  What: Coatue reduced position by 35% (Q4 13F, filed       ││
│  │        2026-02-13). Lone Pine initiated new 1.2% position. ││
│  │  Why it matters: Coatue was #2 HF holder. HF concentration ││
│  │        dropped from 22% to 19% of float. Crowding risk     ││
│  │        decreasing.                                          ││
│  │  Claims impacted: None directly.                            ││
│  │  Kill criteria: None affected.                              ││
│  │  Data note: 13F reports Q4 holdings; 45-day lag.            ││
│  │  [View 13F detail →]                                        ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─ DDOG ── Kill criterion approaching ─── ⚠ WATCH ── 06:00 ─┐│
│  │  What: Net Revenue Retention reported at 107% in Q4 2025   ││
│  │        earnings (10-K p.52). This was 112% in Q3, 118%     ││
│  │        in Q2. Two-quarter downtrend.                        ││
│  │  Why it matters: Kill criterion #2 is "NRR < 105% for 2    ││
│  │        consecutive quarters." One more quarter of decline   ││
│  │        at this rate breaches.                               ││
│  │  Claims impacted: Claim 2 (platform expansion drives       ││
│  │        dollar retention) — CHALLENGED                       ││
│  │  Kill criteria: #2 moved from OK → WATCH                   ││
│  │  [View Decision Brief →]  [View 10-K section →]            ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  YESTERDAY — Feb 13, 2026                                       │
│  [...]                                                          │
└─────────────────────────────────────────────────────────────────┘
```

#### Change Event Data Model

```python
@dataclass
class ChangeEvent:
    id: str
    ticker: str
    timestamp: datetime
    severity: str                   # "info", "watch", "breach"

    # What changed
    event_type: str                 # "filing", "13f_shift", "insider_txn",
                                    # "kpi_update", "kill_criterion_move",
                                    # "catalyst_occurred", "price_event"
    what_changed: str               # plain English summary
    source: Citation

    # Why it matters
    interpretation: str             # 1-2 sentences
    interpretation_is_fact: bool    # False = this is editorial, flagged as such

    # Claim linkage
    claims_impacted: list[str]      # claim IDs
    claim_impact: str               # "supports", "neutral", "challenges"
    kill_criteria_impacted: list[str]
    kill_status_change: str | None  # "ok→watch", "watch→breach", etc.

    # Traceability
    raw_data: dict                  # the underlying numbers
    computation: str | None         # if derived, how
```

#### Change Detection Pipeline

```python
class ChangeDetector:
    """
    Runs on schedule. Compares current state to last-known state.
    Produces ChangeEvents only when something actually changed.
    """

    def __init__(self, db, llm_client):
        self.db = db
        self.llm = llm_client

    async def detect_changes(self, ticker: str) -> list[ChangeEvent]:
        events = []

        # 1. New SEC filings since last check
        new_filings = await self.check_new_filings(ticker)
        for filing in new_filings:
            event = await self.process_filing(ticker, filing)
            events.append(event)

        # 2. 13F ownership shifts (quarterly, but check daily for new filings)
        ownership_changes = await self.check_13f_changes(ticker)
        for change in ownership_changes:
            events.append(self.process_ownership_change(ticker, change))

        # 3. Insider transactions (Forms 3/4/5)
        insider_txns = await self.check_insider_transactions(ticker)
        for txn in insider_txns:
            events.append(self.process_insider_txn(ticker, txn))

        # 4. KPI updates from latest filings
        kpi_updates = await self.check_kpi_updates(ticker)
        for update in kpi_updates:
            events.append(update)

        # 5. Kill criteria status checks
        kill_moves = await self.check_kill_criteria(ticker)
        for move in kill_moves:
            events.append(move)

        # 6. Link each event to active claims
        active_thesis = await self.db.get_active_thesis(ticker)
        if active_thesis:
            for event in events:
                event.claims_impacted = self.match_event_to_claims(
                    event, active_thesis.claims
                )

        return sorted(events, key=lambda e: e.severity_rank(), reverse=True)

    async def process_filing(self, ticker: str, filing: dict) -> ChangeEvent:
        """
        LLM reads the filing and extracts what changed.
        The LLM's job here is summarization + claim linkage, NOT judgment.
        """
        filing_text = await self.fetch_filing_text(filing['accession_number'])
        active_thesis = await self.db.get_active_thesis(ticker)

        prompt = f"""You are extracting factual deltas from a new SEC filing.

Filing type: {filing['form_type']}
Ticker: {ticker}
Filed: {filing['filing_date']}

Active thesis claims being monitored:
{json.dumps([c.__dict__ for c in active_thesis.claims], default=str) if active_thesis else "None"}

Active kill criteria:
{json.dumps([k.__dict__ for k in active_thesis.kill_criteria], default=str) if active_thesis else "None"}

Instructions:
1. Identify the 1-3 most material new facts in this filing.
2. For each fact: state what changed, cite the exact section/page, and note the prior value if known.
3. If any fact impacts an active claim, state which claim and whether it supports or challenges it.
4. If any fact moves a kill criterion closer to or further from its threshold, flag it.
5. SEPARATE facts from interpretation. Label interpretation explicitly.
6. Do NOT provide buy/sell recommendations.

Respond in JSON:
{{
  "material_facts": [
    {{
      "what": "...",
      "section": "...",
      "page": ...,
      "prior_value": "...",
      "new_value": "...",
      "claims_impacted": ["claim_id"],
      "claim_impact": "supports|challenges|neutral",
      "kill_criteria_impacted": ["kc_id"],
      "interpretation": "...",  // labeled as interpretation
    }}
  ]
}}

Filing text:
{filing_text[:80000]}"""

        response = self.llm.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )

        return self.parse_filing_events(ticker, filing, response)
```

---

### Surface 3: Thesis Builder + Monitor

The workflow that turns an idea into a monitored position. Chat is the input method. Structured cards are the output.

#### Chat as Controller

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  LEFT PANEL: Chat                    RIGHT PANEL: Pinned Cards  │
│  ─────────────────                   ─────────────────────────  │
│                                                                  │
│  > /thesis ASML Long — EUV           ┌─ PINNED THESIS ────────┐│
│    attach rate inflects as            │ ASML — Long            ││
│    leading-edge ramp drives           │                        ││
│    services mix + margin              │ Claim 1: EUV attach    ││
│    expansion.                         │   KPI: EUV % of litho  ││
│                                       │   Kill: < 65% for 2Q   ││
│  ┌─ THESIS DRAFT ──────────┐         │                        ││
│  │                          │         │ Claim 2: Services mix  ││
│  │ I've decomposed your     │         │   KPI: Services % rev  ││
│  │ thesis into 3 claims:    │         │   Kill: < 22% for 2Q   ││
│  │                          │         │                        ││
│  │ 1. EUV attach rate rises │         │ Claim 3: Gross margin  ││
│  │    from 72% to 85%+ by   │         │   KPI: Gross margin %  ││
│  │    2028                   │         │   Kill: < 50% for 2Q   ││
│  │    KPI: EUV % of litho   │         │                        ││
│  │    revenue                │         │ Status: MONITORING     ││
│  │    Source: 10-K p.34      │         │ Since: 2026-02-14      ││
│  │    Proposed kill: < 65%   │         └────────────────────────┘│
│  │    for 2 quarters         │                                   │
│  │                          │         ┌─ PINNED CHANGE LOG ────┐│
│  │ 2. Services/installed    │         │ Last 7 days:           ││
│  │    base grows to 30% of  │         │ • 8-K: €2.8B prepay   ││
│  │    revenue (from 24%)    │         │   → Supports Claim 1   ││
│  │    [...]                 │         │ • Form 4: CFO sale     ││
│  │                          │         │   → Routine (10b5-1)   ││
│  │ 3. Gross margin reprices │         └────────────────────────┘│
│  │    to 55-57% as mix      │                                   │
│  │    shifts                │         ┌─ PINNED EVIDENCE ──────┐│
│  │    [...]                 │         │ Claim 1 citations:     ││
│  │                          │         │ • 10-K p.34: "EUV..."  ││
│  │ Edit any of these before │         │ • TSMC 10-K p.12: ...  ││
│  │ I lock them in.          │         │ • 8-K (Nov 2): Intel   ││
│  └──────────────────────────┘         └────────────────────────┘│
│                                                                  │
│  > Adjust kill #1 to < 60%           ┌─ PINNED MODEL INPUTS ──┐│
│    for 3 quarters. Also add          │ EV Build:              ││
│    a kill on China revenue           │   Mkt cap: €312B       ││
│    exceeding 40%.                    │   + Debt: €5.1B        ││
│                                       │   - Cash: €9.2B        ││
│  ┌─ UPDATED ───────────────┐         │   = EV: €308B          ││
│  │ Kill criteria updated:   │         │ Source: 10-K p.63      ││
│  │ #1: EUV attach < 60%    │         │                        ││
│  │     for 3Q (was <65%/2Q) │         │ FCF: €4.2B             ││
│  │ #4 added: China rev      │         │ Source: 10-K p.47      ││
│  │     > 40% for any Q      │         │ Def: OpCF - CapEx      ││
│  │                          │         │                        ││
│  │ Thesis locked. Monitoring│         │ WACC: 8.1%             ││
│  │ active.                  │         │ rf:3.8% + β1.12×4.5%  ││
│  └──────────────────────────┘         └────────────────────────┘│
│                                                                  │
│  > /update ASML since:2026-02-01                                │
│  > /evidence ASML-C1                                            │
│  > /alert ASML gross_margin < 50% 2Q                            │
│  > /stress "margin expansion is already consensus"               │
│  > /export memo                                                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### Command Set

```python
COMMANDS = {
    # Thesis lifecycle
    "/thesis": {
        "usage": "/thesis <TICKER> <direction> — <plain English thesis>",
        "action": "Decomposes thesis into 2-4 claims with KPIs, sources, "
                  "proposed kill criteria, and next catalysts. Returns draft "
                  "for user to edit before locking.",
        "output": "Thesis draft card (editable)"
    },
    "/lock": {
        "usage": "/lock <TICKER>",
        "action": "Locks current thesis draft. Starts monitoring all claims "
                  "and kill criteria. Cannot be undone without /close.",
        "output": "Pinned Thesis card (monitoring)"
    },
    "/close": {
        "usage": "/close <TICKER> [reason]",
        "action": "Closes thesis. Records outcome for calibration tracking.",
        "output": "Archived thesis with performance record"
    },

    # Daily workflow
    "/update": {
        "usage": "/update <TICKER> since:<YYYY-MM-DD>",
        "action": "Pulls all changes since date. Returns delta-only summary "
                  "linked to claims and kill criteria.",
        "output": "Change log card"
    },
    "/brief": {
        "usage": "/brief <TICKER>",
        "action": "Generates or refreshes full Decision Brief.",
        "output": "Decision Brief (full page)"
    },

    # Evidence and analysis
    "/evidence": {
        "usage": "/evidence <CLAIM_ID>",
        "action": "Returns all citations supporting and disconfirming this claim. "
                  "Includes exact filing excerpts with page numbers.",
        "output": "Evidence card (cited)"
    },
    "/stress": {
        "usage": "/stress <statement or paste memo bullets>",
        "action": "Adversarial PM mode. Identifies: what's circular, what's priced in, "
                  "what would falsify it, missing disconfirming evidence, "
                  "and the 2 questions a PM will ask.",
        "output": "Stress test card"
    },
    "/filing": {
        "usage": "/filing <TICKER> <query>",
        "action": "Retrieves exact filing language matching the query. "
                  "e.g., '/filing ASML customer concentration'",
        "output": "Cited excerpts card"
    },

    # Monitoring
    "/alert": {
        "usage": "/alert <TICKER> <metric> <operator> <threshold> [duration]",
        "action": "Sets monitoring rule. Triggers in What Changed feed "
                  "when threshold is approached (80%) or breached.",
        "output": "Alert confirmation"
    },
    "/watchlist": {
        "usage": "/watchlist add|remove <TICKER>",
        "action": "Manages watchlist. Watchlist names appear in What Changed feed.",
        "output": "Watchlist confirmation"
    },

    # Export
    "/export": {
        "usage": "/export memo|brief|claims [format:pdf|md]",
        "action": "Exports current thesis or brief to PDF or markdown. "
                  "Formatted for IC doc / email paste.",
        "output": "Downloadable file"
    }
}
```

---

## Industry Templates

Generic metrics across sectors create false signals. Each sector gets its own KPI pack, accounting adjustments, and kill-criteria primitives.

### Template Structure

```python
@dataclass
class SectorTemplate:
    sector: str
    display_name: str

    # Primary KPIs for claims (what PMs actually track in this sector)
    primary_kpis: list[KPIDefinition]

    # Accounting adjustments (sector-specific normalizations)
    accounting_adjustments: list[AccountingAdjustment]

    # Default kill criteria primitives (starting points, user edits)
    default_kill_criteria: list[KillCriterionTemplate]

    # Valuation approach (which method is primary for this sector)
    primary_valuation: str          # "dcf", "ev_ebitda", "p_b_roe", "ev_revenue"
    valuation_notes: str            # sector-specific guidance

    # Scores to include vs exclude
    include_scores: list[str]       # which generic scores apply
    exclude_scores: list[str]       # which would be misleading
    exclude_reason: dict[str, str]  # why each excluded score is misleading


SECTOR_TEMPLATES = {

    "saas": SectorTemplate(
        sector="saas",
        display_name="SaaS / Cloud Software",
        primary_kpis=[
            KPIDefinition("nrr", "Net Revenue Retention", "%",
                          "Annual recurring revenue from existing customers YoY. "
                          "Source: typically in 10-K revenue discussion or S-1.",
                          alert_below=105),
            KPIDefinition("cac_payback", "CAC Payback Period", "months",
                          "S&M spend / (net new ARR × gross margin). "
                          "Compute from: 10-K SGA breakdown + ARR disclosure.",
                          alert_above=24),
            KPIDefinition("rule_of_40", "Rule of 40", "%",
                          "Revenue growth % + FCF margin %. "
                          "Source: computed from 10-K revenue + cash flow statement.",
                          alert_below=30),
            KPIDefinition("gross_margin", "Gross Margin", "%",
                          "Source: 10-K income statement. "
                          "Adjust: exclude SBC from COGS if material.",
                          alert_below=70),
            KPIDefinition("sbc_revenue", "SBC / Revenue", "%",
                          "Stock-based compensation as % of revenue. "
                          "Source: 10-K cash flow statement or compensation note.",
                          alert_above=25),
            KPIDefinition("dbnrr", "Dollar-Based NRR", "%",
                          "If disclosed separately from NRR.",
                          alert_below=110),
            KPIDefinition("remaining_performance_obligations", "RPO", "$",
                          "Contracted future revenue. Source: 10-K revenue note.",
                          alert_direction="declining_yoy"),
        ],
        accounting_adjustments=[
            AccountingAdjustment(
                name="SBC normalization",
                description="SaaS companies often have SBC at 15-30% of revenue. "
                            "FCF looks great but earnings are diluted. Always compute "
                            "FCF-minus-SBC as the 'real' free cash flow.",
                computation="adjusted_fcf = reported_fcf - sbc_expense"
            ),
            AccountingAdjustment(
                name="Capitalized software costs",
                description="Some SaaS companies capitalize development costs, "
                            "inflating operating income. Check 10-K intangibles note.",
                computation="adjusted_opex = reported_opex + capitalized_dev_costs"
            ),
        ],
        default_kill_criteria=[
            KillCriterionTemplate("NRR < 105% for 2 consecutive quarters",
                                  "nrr", "<", 105, "2Q"),
            KillCriterionTemplate("CAC payback > 30 months",
                                  "cac_payback", ">", 30, "1Q"),
            KillCriterionTemplate("SBC/Revenue > 30% and rising",
                                  "sbc_revenue", ">", 30, "2Q"),
            KillCriterionTemplate("Rule of 40 < 25% for 2 consecutive quarters",
                                  "rule_of_40", "<", 25, "2Q"),
        ],
        primary_valuation="ev_revenue",
        valuation_notes="EV/Revenue or EV/NTM Revenue is primary. "
                        "DCF works but terminal value dominates — use with caution. "
                        "Always pair with Rule of 40 to judge if multiple is deserved.",
        include_scores=["beneish_m"],  # Earnings manipulation still relevant
        exclude_scores=["altman_z", "piotroski_f", "greenblatt"],
        exclude_reason={
            "altman_z": "Designed for manufacturing firms. Working capital and "
                        "retained earnings ratios are meaningless for SaaS.",
            "piotroski_f": "Asset turnover and leverage metrics don't apply. "
                           "SaaS is asset-light with negative working capital by design.",
            "greenblatt": "EBIT/EV is often negative for growth SaaS. "
                          "Ranking by earnings yield would exclude the best companies."
        }
    ),

    "banks": SectorTemplate(
        sector="banks",
        display_name="Banks / Financials",
        primary_kpis=[
            KPIDefinition("nim", "Net Interest Margin", "%",
                          "Net interest income / avg earning assets. "
                          "Source: 10-K interest income table.",
                          alert_below=2.5),
            KPIDefinition("cet1", "CET1 Capital Ratio", "%",
                          "Common Equity Tier 1 / Risk-Weighted Assets. "
                          "Source: 10-K capital adequacy note.",
                          alert_below=10),
            KPIDefinition("efficiency_ratio", "Efficiency Ratio", "%",
                          "Non-interest expense / (net interest income + non-interest income). "
                          "Lower is better. Source: 10-K income statement.",
                          alert_above=65),
            KPIDefinition("nco_rate", "Net Charge-Off Rate", "%",
                          "Net charge-offs / average loans. "
                          "Source: 10-K credit quality tables.",
                          alert_above=1.0),
            KPIDefinition("rotce", "Return on Tangible Common Equity", "%",
                          "Net income / avg tangible common equity. "
                          "Source: computed from 10-K balance sheet.",
                          alert_below=12),
            KPIDefinition("loan_growth", "Loan Growth", "% YoY",
                          "Total loans YoY change. Source: 10-K balance sheet.",
                          alert_direction="context_dependent"),
            KPIDefinition("npa_ratio", "Non-Performing Assets Ratio", "%",
                          "NPAs / total assets. Source: 10-K credit quality note.",
                          alert_above=1.5),
        ],
        accounting_adjustments=[
            AccountingAdjustment(
                name="Provision normalization",
                description="Provisions for credit losses are inherently cyclical "
                            "and management has discretion over timing. Use mid-cycle "
                            "NCO rate × loan book for normalized earnings.",
                computation="normalized_provision = avg_5yr_nco_rate × current_loans"
            ),
            AccountingAdjustment(
                name="AOCI adjustment",
                description="Unrealized losses on HTM/AFS securities affect tangible "
                            "book value but not regulatory capital (for large banks). "
                            "Always check both GAAP and adjusted TBV.",
                computation="adjusted_tbv = reported_tbv + aoci_securities_losses"
            ),
        ],
        default_kill_criteria=[
            KillCriterionTemplate("CET1 < 9% (approaching regulatory minimums)",
                                  "cet1", "<", 9.0, "1Q"),
            KillCriterionTemplate("NCO rate > 2% for 2 consecutive quarters",
                                  "nco_rate", ">", 2.0, "2Q"),
            KillCriterionTemplate("NIM compression > 50bps YoY without offsetting fee growth",
                                  "nim", "yoy_decline_bps >", 50, "2Q"),
            KillCriterionTemplate("Efficiency ratio > 70%",
                                  "efficiency_ratio", ">", 70, "2Q"),
        ],
        primary_valuation="p_b_roe",
        valuation_notes="Price/Tangible Book Value vs ROTCE is the primary framework. "
                        "A bank earning above COE deserves P/TBV > 1.0x. "
                        "DCF is unreliable for banks due to provision timing.",
        include_scores=[],
        exclude_scores=["altman_z", "piotroski_f", "greenblatt", "beneish_m"],
        exclude_reason={
            "altman_z": "Designed for non-financial corporates. Leverage ratios "
                        "are meaningless for banks where leverage IS the business.",
            "piotroski_f": "Leverage and working capital tests don't apply to banks.",
            "greenblatt": "EBIT and invested capital are undefined for banks. "
                          "Use P/TBV vs ROTCE instead.",
            "beneish_m": "Accruals-based. Banks have loan loss provisions that "
                          "would trigger false positives constantly."
        }
    ),

    "semis": SectorTemplate(
        sector="semis",
        display_name="Semiconductors",
        primary_kpis=[
            KPIDefinition("backlog", "Order Backlog", "$",
                          "Unfilled orders. Source: 10-K order/backlog discussion "
                          "or earnings release.",
                          alert_direction="declining_qoq"),
            KPIDefinition("gross_margin", "Gross Margin", "%",
                          "Source: 10-K income statement. "
                          "Critical to decompose: mix vs ASP vs utilization.",
                          alert_below=None),  # Sector-specific, varies widely
            KPIDefinition("book_to_bill", "Book-to-Bill Ratio", "x",
                          "New orders / revenue. >1.0 = expanding. "
                          "Source: earnings release or 10-Q.",
                          alert_below=0.9),
            KPIDefinition("inventory_days", "Inventory Days", "days",
                          "Inventory / (COGS/365). Rising inventory days = "
                          "demand softening or channel stuffing. Source: 10-K.",
                          alert_above=None),  # Depends on cycle position
            KPIDefinition("capex_intensity", "CapEx / Revenue", "%",
                          "Capital intensity. Source: 10-K cash flow statement.",
                          alert_above=None),  # Varies by fabless vs IDM
            KPIDefinition("r_and_d_intensity", "R&D / Revenue", "%",
                          "Innovation spend. Source: 10-K income statement.",
                          alert_direction="context_dependent"),
            KPIDefinition("revenue_per_wafer", "Revenue per Wafer Start", "$",
                          "For fabs/foundries. Proxy for mix richness.",
                          alert_direction="declining_qoq"),
        ],
        accounting_adjustments=[
            AccountingAdjustment(
                name="Cycle normalization",
                description="Semi earnings are deeply cyclical. Use mid-cycle "
                            "margins (avg of last full cycle, typically 3-5 years) "
                            "for valuation. Trailing P/E is misleading at cycle peaks/troughs.",
                computation="normalized_eps = mid_cycle_margin × current_revenue / shares"
            ),
            AccountingAdjustment(
                name="Gross margin bridge",
                description="Decompose gross margin changes into: (1) product mix, "
                            "(2) ASP changes, (3) utilization rate, (4) input costs. "
                            "Management often provides this in earnings calls.",
                computation="See earnings call transcript for management bridge"
            ),
        ],
        default_kill_criteria=[
            KillCriterionTemplate("Backlog declines >15% QoQ",
                                  "backlog", "qoq_decline >", 15, "1Q"),
            KillCriterionTemplate("Book-to-bill < 0.85 for 2 consecutive quarters",
                                  "book_to_bill", "<", 0.85, "2Q"),
            KillCriterionTemplate("Inventory days > 120 and rising",
                                  "inventory_days", ">", 120, "2Q"),
            KillCriterionTemplate("Gross margin below mid-cycle average by >500bps",
                                  "gross_margin", "below_midcycle_bps >", 500, "2Q"),
        ],
        primary_valuation="ev_ebitda",
        valuation_notes="EV/EBITDA on normalized (mid-cycle) earnings is primary. "
                        "P/E on trailing is deceptive at cycle turns. "
                        "For equipment companies (ASML, KLAC), backlog visibility "
                        "justifies forward estimates. For commodity semis, "
                        "use EV/normalized EBITDA through the cycle.",
        include_scores=["piotroski_f", "beneish_m"],
        exclude_scores=["altman_z"],
        exclude_reason={
            "altman_z": "Working capital fluctuates with inventory cycle. "
                        "Would flag distress at cycle troughs when stocks are cheapest."
        }
    ),

    "e_and_p": SectorTemplate(
        sector="e_and_p",
        display_name="Oil & Gas E&P",
        primary_kpis=[
            KPIDefinition("production_growth", "Production Growth", "% YoY (BOE/d)",
                          "Source: 10-K operations review.",
                          alert_direction="context_dependent"),
            KPIDefinition("finding_cost", "Finding & Development Cost", "$/BOE",
                          "All-in cost to find and develop reserves. "
                          "Source: computed from 10-K reserve + cost data.",
                          alert_above=None),
            KPIDefinition("reserve_replacement", "Reserve Replacement Ratio", "%",
                          "New reserves added / production. >100% = sustainable. "
                          "Source: 10-K reserves table (SMOG disclosure).",
                          alert_below=80),
            KPIDefinition("breakeven_price", "Corporate Breakeven Oil Price", "$/bbl",
                          "Price needed to cover all costs + maintenance capex. "
                          "Source: derived from 10-K cost structure.",
                          alert_above=None),
            KPIDefinition("net_debt_ebitdax", "Net Debt / EBITDAX", "x",
                          "Leverage metric. Source: 10-K balance sheet + income stmt. "
                          "EBITDAX = EBITDA + exploration expense.",
                          alert_above=2.5),
            KPIDefinition("fcf_yield_at_strip", "FCF Yield at Strip Pricing", "%",
                          "What the company generates at current futures curve. "
                          "Source: derived from hedging disclosure + cost structure.",
                          alert_below=5),
        ],
        accounting_adjustments=[
            AccountingAdjustment(
                name="Successful efforts vs full cost",
                description="Companies using full cost method capitalize dry holes, "
                            "inflating assets. Always check which method is used "
                            "(10-K accounting policies note) and adjust comparisons.",
                computation="If full_cost: add back ceiling_test_writedowns to earnings history"
            ),
            AccountingAdjustment(
                name="Hedging book adjustment",
                description="E&Ps with significant hedging may report realized prices "
                            "well above or below spot. Check hedging disclosure for "
                            "forward commitments. Source: 10-K derivatives note.",
                computation="realized_price = reported_revenue / production_volumes"
            ),
        ],
        default_kill_criteria=[
            KillCriterionTemplate("Net Debt/EBITDAX > 3.0x",
                                  "net_debt_ebitdax", ">", 3.0, "1Q"),
            KillCriterionTemplate("Reserve replacement < 60% for 2 years",
                                  "reserve_replacement", "<", 60, "2Y"),
            KillCriterionTemplate("Breakeven above current strip by >$15/bbl",
                                  "breakeven_vs_strip", ">", 15, "1Q"),
        ],
        primary_valuation="nav",
        valuation_notes="Net Asset Value (PV of proved + probable reserves at strip pricing) "
                        "is the primary framework. EV/EBITDA is secondary. "
                        "P/E is misleading due to DD&A and impairment noise.",
        include_scores=["altman_z"],  # Actually relevant for E&P distress
        exclude_scores=["greenblatt", "piotroski_f"],
        exclude_reason={
            "greenblatt": "ROIC is distorted by reserve writedowns and DD&A methodology. "
                          "Capital intensity makes comparison to non-commodity sectors meaningless.",
            "piotroski_f": "Asset turnover and margin trends are commodity-price-driven, "
                           "not management-quality-driven. Would produce random signals."
        }
    ),
}
```

---

## Revised Computation Engines

The engines remain, but their outputs are reshaped to serve the Decision Brief rather than produce standalone dashboards.

### Engine 1 (Quant) — Now Serves: "What's Priced In" + Model Inputs Card

```python
class QuantEngine:
    """
    No longer produces a standalone dashboard.
    Outputs:
    1. MarketImplied object (for Position & Variant Perception)
    2. Cited model inputs (for Model Inputs card)
    3. Sector-appropriate quality/red-flag scores
    """

    def analyze(self, ticker: str, template: SectorTemplate) -> QuantOutput:

        financials = self.fetch_financials(ticker)  # OpenBB + SEC XBRL
        prices = self.fetch_prices(ticker)

        # 1. Build EV with full audit trail
        ev_build = self.build_ev(ticker, financials)
        # Returns: {"market_cap": X, "source": Citation, "total_debt": Y, ...}
        # Every component has a Citation attached

        # 2. Reverse DCF (what's priced in)
        # Uses sector-appropriate valuation method
        if template.primary_valuation == "dcf":
            market_implied = self.reverse_dcf(ticker, ev_build, financials)
        elif template.primary_valuation == "ev_ebitda":
            market_implied = self.reverse_ev_ebitda(ticker, ev_build, financials)
        elif template.primary_valuation == "p_b_roe":
            market_implied = self.reverse_p_tbv(ticker, financials)
        elif template.primary_valuation == "ev_revenue":
            market_implied = self.reverse_ev_revenue(ticker, ev_build, financials)
        elif template.primary_valuation == "nav":
            market_implied = self.nav_analysis(ticker, financials)

        # 3. Only run applicable quality scores
        scores = {}
        for score_name in template.include_scores:
            scores[score_name] = self.compute_score(score_name, financials)
        # Attach reasons for excluded scores
        excluded = {name: reason for name, reason in template.exclude_reason.items()}

        # 4. Sector KPIs — compute each one with citation
        sector_kpis = {}
        for kpi_def in template.primary_kpis:
            sector_kpis[kpi_def.id] = self.compute_kpi(
                ticker, kpi_def, financials
            )
            # Each KPI result includes: value, qoq_delta, yoy_delta, Citation

        # 5. Accounting adjustments
        adjusted_financials = self.apply_adjustments(
            financials, template.accounting_adjustments
        )

        return QuantOutput(
            market_implied=market_implied,
            ev_build=ev_build,
            sector_kpis=sector_kpis,
            quality_scores=scores,
            excluded_scores=excluded,
            adjusted_financials=adjusted_financials,
            raw_financials=financials,  # Always available for audit
        )
```

### Engine 2 (Flow) — Now Serves: Holder Map + Change Feed Context

```python
class FlowEngine:
    """
    No longer claims to generate alpha signals.
    Outputs:
    1. HolderMap (who owns it, concentration, changes — context only)
    2. Insider activity with filters (10b5-1 vs discretionary, size vs comp)
    3. Change events for the What Changed feed
    """

    def analyze(self, ticker: str) -> FlowOutput:

        # 1. Institutional holder map from 13F
        holders = self.build_holder_map(ticker)
        # Explicitly labeled: "13F data is 45 days lagged. This shows
        # Q4 2025 positions as of filing deadline."

        # 2. Insider transactions — filtered and contextualized
        raw_insiders = self.fetch_insider_transactions(ticker)
        filtered = self.filter_insider_transactions(raw_insiders)

        # 3. Short interest (descriptive only)
        short_data = self.fetch_short_interest(ticker)

        return FlowOutput(
            holder_map=holders,
            insider_activity=filtered,
            short_interest=short_data,
            data_freshness={
                "13f_as_of": holders.report_date,
                "13f_lag_note": "13F filings report quarter-end holdings "
                                "with a 45-day filing deadline.",
                "insider_as_of": filtered[-1].filing_date if filtered else None,
                "short_as_of": short_data.report_date,
            }
        )

    def filter_insider_transactions(self, transactions: list) -> list:
        """
        Critical filtering that the original plan lacked.
        Not all insider transactions are meaningful.
        """
        filtered = []
        for txn in transactions:

            # Classify transaction
            txn.is_10b5_1 = self.detect_10b5_1(txn)
            txn.is_discretionary = not txn.is_10b5_1
            txn.pct_of_holdings = (txn.shares / txn.shares_owned_after
                                    if txn.shares_owned_after else None)
            txn.pct_of_annual_comp = self.estimate_comp_ratio(txn)

            # Contextual note
            if txn.is_10b5_1:
                txn.context_note = (
                    f"10b5-1 plan transaction. Represents "
                    f"{txn.pct_of_holdings:.1%} of holdings. "
                    f"Routine unless plan was recently adopted/modified."
                )
            elif txn.transaction_type == 'S' and txn.pct_of_holdings and txn.pct_of_holdings < 0.05:
                txn.context_note = (
                    f"Discretionary sale but small ({txn.pct_of_holdings:.1%} of holdings). "
                    f"Likely tax or liquidity-driven."
                )
            elif txn.transaction_type == 'P' and txn.is_discretionary:
                txn.context_note = (
                    f"Discretionary purchase by {txn.insider_title}. "
                    f"Value: ${txn.value:,.0f} ({txn.pct_of_holdings:.1%} increase in holdings)."
                )
                # This is the only type that's genuinely informative
                txn.is_notable = True
            else:
                txn.is_notable = False

            txn.source = Citation(
                source_type="form4",
                filer=txn.insider_name,
                filing_date=txn.filing_date,
                section="Statement of Changes in Beneficial Ownership",
                accession_number=txn.accession_number,
                url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={txn.cik}&type=4",
            )

            filtered.append(txn)

        return filtered

    def build_holder_map(self, ticker: str) -> HolderMap:
        """
        Holder mapping for crowding and context, not "smart money signal."
        """
        holdings_13f = self.fetch_13f_holdings(ticker)

        # Classify each holder
        for h in holdings_13f:
            h.fund_type = self.classify_fund(h.filer_name, h.filer_cik)
            # "hedge_fund", "long_only", "index", "quant", "activist"

        # Compute concentration
        hf_holdings = [h for h in holdings_13f if h.fund_type == "hedge_fund"]
        total_float = self.get_float(ticker)
        hf_pct = sum(h.shares for h in hf_holdings) / total_float if total_float else 0

        # Compute overlap (how many of the same funds own the same names)
        peer_tickers = self.get_sector_peers(ticker)
        overlap_scores = self.compute_holder_overlap(ticker, peer_tickers, holdings_13f)

        return HolderMap(
            top_hf_holders=sorted(hf_holdings, key=lambda h: h.value, reverse=True)[:10],
            hf_concentration=hf_pct,
            hf_concentration_percentile=self.percentile_vs_sector(hf_pct, ticker),
            qoq_changes=[h for h in holdings_13f if abs(h.change_pct) > 0.10],
            overlap_with_peers=overlap_scores,
            data_lag_note=f"Based on 13F filings for Q4 2025 "
                          f"(45-day lag from quarter end).",
        )
```

### Engine 3 (Qualitative) — Now Serves: Claims Evidence + Red Flags

```python
class QualitativeEngine:
    """
    No longer produces Collins framework scores as standalone metrics.
    Instead:
    1. Provides cited evidence for/against user's claims
    2. Detects red flags from filings (with citations)
    3. Answers targeted filing queries (/filing command)
    """

    def __init__(self, llm_client):
        self.llm = llm_client

    async def build_evidence_for_claims(
        self, ticker: str, claims: list[Claim], filing_text: str
    ) -> dict:
        """
        Given user's claims, searches filings for supporting
        and disconfirming evidence. Every output is cited.
        """

        prompt = f"""You are a research associate at a fundamental equity fund.
Your job is to find evidence in SEC filings — both supporting and disconfirming.
You are NOT making investment recommendations. You are gathering cited evidence.

CRITICAL RULES:
1. Every claim you make must include: the exact section name, page number,
   and a brief quote or paraphrase from the filing.
2. If you cannot find evidence for a claim, say "No direct evidence found in
   this filing" — do NOT fabricate or infer.
3. Clearly separate FACTS (what the filing says) from INTERPRETATION
   (what it might mean). Label each.
4. Actively look for disconfirming evidence. Your job is to be balanced,
   not to support the thesis.

Ticker: {ticker}
Claims to evaluate:
{json.dumps([{{"id": c.id, "statement": c.statement, "kpi": c.kpi}} for c in claims], indent=2)}

For each claim, provide:
{{
  "claim_id": "...",
  "supporting_evidence": [
    {{
      "fact": "what the filing says (paraphrase or brief quote)",
      "section": "exact section name",
      "page": page_number,
      "type": "fact"
    }},
    {{
      "statement": "what this might imply for the claim",
      "type": "interpretation"
    }}
  ],
  "disconfirming_evidence": [...same format...],
  "evidence_strength": "strong|moderate|weak|none"
}}

Filing text:
{filing_text[:80000]}"""

        response = self.llm.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )

        return json.loads(response.content[0].text)

    async def detect_red_flags(
        self, ticker: str, filing_text: str, template: SectorTemplate
    ) -> list[RedFlag]:
        """
        Sector-aware red flag detection.
        Every flag is cited with filing section + page.
        """

        prompt = f"""You are an auditor reviewing a {template.display_name} company's 10-K
for potential red flags. Check for the following sector-specific issues:

Sector: {template.display_name}
Ticker: {ticker}

SECTOR-SPECIFIC RED FLAGS TO CHECK:
{self.get_sector_red_flag_checklist(template)}

UNIVERSAL RED FLAGS:
- Revenue recognition policy changes
- Growing GAAP vs non-GAAP earnings gap
- Related party transactions
- Auditor changes or going concern language
- Material weakness in internal controls
- Unusual increase in "other" income/expense
- Receivables growing faster than revenue (DSO expansion)
- Changes in accounting estimates (useful life, reserves)

For each red flag found:
{{
  "flag": "description",
  "severity": "high|medium|low",
  "section": "filing section",
  "page": page_number,
  "evidence": "what specifically triggered this flag",
  "context": "why this matters or might not matter",
  "type": "fact"  // always fact for red flags — what the filing says
}}

If no red flags found in a category, do not include it.
Only flag things you can cite directly from the filing.

Filing text:
{filing_text[:80000]}"""

        response = self.llm.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )

        return self.parse_red_flags(response)

    async def targeted_filing_query(
        self, ticker: str, query: str, filing_text: str
    ) -> list[Citation]:
        """
        Serves the /filing command.
        User asks: "Show me the exact 10-K language on customer concentration"
        Returns: cited excerpts.
        """

        prompt = f"""Find the exact language in this filing that addresses:
"{query}"

Return 1-5 relevant passages. For each:
{{
  "excerpt": "exact or near-exact quote from filing (keep under 200 words)",
  "section": "section name",
  "page": page_number,
  "relevance": "brief note on why this passage is relevant to the query"
}}

If nothing relevant is found, return an empty array.
Do NOT paraphrase or interpret — return the filing's own language.

Filing text:
{filing_text[:80000]}"""

        response = self.llm.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        return self.parse_excerpts(ticker, response)
```

---

## Adversarial PM Mode (/stress)

```python
async def stress_test(self, ticker: str, memo_text: str,
                       quant: QuantOutput, flow: FlowOutput) -> dict:
    """
    User pastes their memo bullets.
    Returns: what's circular, what's priced, what would falsify,
    missing disconfirming evidence, and the 2 questions a PM will ask.
    """

    prompt = f"""You are a senior PM at a $5B long/short equity fund. An analyst
just pitched you {ticker} with the following memo bullets:

---
{memo_text}
---

Your quantitative team has provided:
- Market-implied growth (reverse DCF): {quant.market_implied.reverse_dcf_growth:.1%}
- Current consensus growth: {quant.market_implied.consensus_growth:.1%}

Your flow desk reports:
- HF concentration: {flow.holder_map.hf_concentration:.1%} of float
- Notable insider activity: {len([i for i in flow.insider_activity if i.is_notable])} discretionary transactions in last 90 days

Your job is to challenge this pitch. Respond with:

1. CIRCULAR REASONING: Identify any claims that assume their own conclusion
   or use the same evidence to support multiple independent claims.

2. ALREADY PRICED: Based on the reverse DCF, what parts of this thesis
   does the market already agree with? Where is the INCREMENTAL edge,
   if any? Be specific.

3. FALSIFICATION: What 2-3 things would need to happen for this thesis
   to be wrong? The analyst should be able to monitor these.

4. MISSING DISCONFIRMING EVIDENCE: What has the analyst NOT addressed
   that a skeptic would raise? What data did they leave out?

5. THE TWO PM QUESTIONS: What are the two toughest questions you'd ask
   in the IC meeting that this memo doesn't answer?

Be direct. No pleasantries. Format as JSON:
{{
  "circular_reasoning": [...],
  "already_priced": "...",
  "falsification_tests": [...],
  "missing_disconfirming": [...],
  "pm_questions": ["...", "..."]
}}"""

    response = self.llm.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )

    return json.loads(response.content[0].text)
```

---

## Database Schema (Revised)

The schema is restructured around theses, claims, and change events rather than generic metric tables.

```sql
-- User's theses (the core object)
CREATE TABLE theses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,
    ticker          VARCHAR(10) NOT NULL,
    direction       VARCHAR(10) NOT NULL,    -- 'long' or 'short'
    thesis_text     TEXT NOT NULL,
    sector_template VARCHAR(30) NOT NULL,    -- links to template
    status          VARCHAR(20) NOT NULL DEFAULT 'draft',
                    -- draft, monitoring, killed, closed
    entry_price     DECIMAL(12,4),
    entry_date      DATE,
    close_price     DECIMAL(12,4),
    close_date      DATE,
    close_reason    TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Claims within a thesis
CREATE TABLE claims (
    id              VARCHAR(20) PRIMARY KEY,  -- e.g., "ASML-C1"
    thesis_id       UUID REFERENCES theses(id),
    statement       TEXT NOT NULL,
    kpi_id          VARCHAR(50) NOT NULL,     -- links to sector template KPI
    current_value   DECIMAL(16,4),
    qoq_delta       DECIMAL(10,4),
    yoy_delta       DECIMAL(10,4),
    status          VARCHAR(20) DEFAULT 'supported',
                    -- supported, mixed, challenged
    last_updated    TIMESTAMPTZ
);

-- Evidence linked to claims
CREATE TABLE evidence (
    id              SERIAL PRIMARY KEY,
    claim_id        VARCHAR(20) REFERENCES claims(id),
    direction       VARCHAR(15) NOT NULL,     -- 'supporting' or 'disconfirming'
    content         TEXT NOT NULL,
    content_type    VARCHAR(15) NOT NULL,     -- 'fact' or 'interpretation'
    source_type     VARCHAR(20) NOT NULL,     -- '10-K', '10-Q', '8-K', etc.
    filer           TEXT,
    filing_date     DATE,
    section         TEXT,
    page            INTEGER,
    accession_number VARCHAR(30),
    url             TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Kill criteria
CREATE TABLE kill_criteria (
    id              VARCHAR(20) PRIMARY KEY,
    thesis_id       UUID REFERENCES theses(id),
    description     TEXT NOT NULL,
    metric          VARCHAR(50) NOT NULL,
    operator        VARCHAR(10) NOT NULL,
    threshold       DECIMAL(16,4) NOT NULL,
    duration        VARCHAR(20),              -- "2Q", "1Y", etc.
    current_value   DECIMAL(16,4),
    current_source  JSONB,                    -- Citation as JSON
    status          VARCHAR(10) DEFAULT 'ok', -- ok, watch, breach
    distance_pct    DECIMAL(10,4),
    watch_reason    TEXT,
    last_updated    TIMESTAMPTZ
);

-- Change events (the feed)
CREATE TABLE change_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          VARCHAR(10) NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    severity        VARCHAR(10) NOT NULL,     -- info, watch, breach
    event_type      VARCHAR(30) NOT NULL,
    what_changed    TEXT NOT NULL,
    source          JSONB NOT NULL,           -- Citation as JSON
    interpretation  TEXT,
    interpretation_is_fact BOOLEAN DEFAULT FALSE,
    claims_impacted JSONB,                    -- array of claim IDs
    claim_impact    VARCHAR(15),
    kill_criteria_impacted JSONB,
    kill_status_change VARCHAR(30),
    raw_data        JSONB
);
CREATE INDEX idx_change_events_ticker ON change_events(ticker, timestamp DESC);
CREATE INDEX idx_change_events_severity ON change_events(severity, timestamp DESC);

-- Catalysts
CREATE TABLE catalysts (
    id              SERIAL PRIMARY KEY,
    thesis_id       UUID REFERENCES theses(id),
    ticker          VARCHAR(10) NOT NULL,
    event_date      DATE NOT NULL,
    event           TEXT NOT NULL,
    claims_tested   JSONB,                    -- array of claim IDs
    kill_criteria_tested JSONB,               -- array of KC IDs
    occurred        BOOLEAN DEFAULT FALSE,
    outcome_notes   TEXT
);

-- Alerts (user-configured monitoring rules)
CREATE TABLE alerts (
    id              SERIAL PRIMARY KEY,
    user_id         UUID NOT NULL,
    ticker          VARCHAR(10) NOT NULL,
    metric          VARCHAR(50) NOT NULL,
    operator        VARCHAR(10) NOT NULL,
    threshold       DECIMAL(16,4) NOT NULL,
    duration        VARCHAR(20),
    is_active       BOOLEAN DEFAULT TRUE,
    last_triggered  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Thesis performance tracking (for calibration over time)
CREATE TABLE thesis_outcomes (
    thesis_id       UUID REFERENCES theses(id) PRIMARY KEY,
    entry_price     DECIMAL(12,4),
    exit_price      DECIMAL(12,4),
    holding_period  INTEGER,                  -- days
    total_return    DECIMAL(10,4),
    exit_reason     VARCHAR(30),              -- kill_triggered, target_reached,
                                              -- thesis_changed, time_stop
    claims_correct  INTEGER,
    claims_total    INTEGER,
    kill_triggered  VARCHAR(20)               -- which kill criterion, if any
);
```

---

## Build Phases (Revised)

### Phase 1: Decision Brief + Quant Engine (Weeks 1-5)

Build the core output first. A user enters a ticker and gets a Decision Brief.

- FastAPI backend + PostgreSQL + OpenBB integration
- Sector template system (start with SaaS + Semis — 2 templates)
- Reverse DCF / EV build with full citation chain
- Sector KPI computation with citations
- Quality scores (only applicable ones per template)
- Decision Brief renderer (API returns structured JSON)
- React frontend: Brief page with all sections
- PDF / markdown export

**Deliverable:** Enter ASML → get a Decision Brief with Market Implied, model inputs, sector KPIs, and red flags. All cited.

### Phase 2: Thesis Builder + Chat Controller (Weeks 6-9)

The thesis workflow: chat decomposes thesis → user edits → monitoring starts.

- `/thesis` command: LLM decomposes into claims + KPIs + kill criteria
- Claims and kill criteria data model + CRUD
- User edit flow (approve, modify, lock)
- `/stress` command: adversarial PM mode
- `/filing` command: targeted filing retrieval
- Chat panel + pinned cards UI layout

**Deliverable:** User types thesis in chat → gets structured claims card → edits and locks → thesis is persisted and monitoring-ready.

### Phase 3: What Changed Feed + Monitoring (Weeks 10-14)

The daily retention product.

- Change detection pipeline (SEC filing watcher, 13F processor, Form 4 parser)
- Change event generation with claim linkage
- Kill criteria status monitoring (ok → watch → breach)
- Alert system
- What Changed feed UI with filters
- `/update` command

**Deliverable:** Daily feed shows filing deltas, ownership shifts, and kill criteria movements, all linked to active claims.

### Phase 4: Flow Context + Holder Map (Weeks 15-17)

Holder mapping as context, not alpha signal.

- 13F parser with fund classification
- Insider transaction filtering (10b5-1 vs discretionary, size vs comp)
- Crowding and overlap computation
- Holder Map section in Decision Brief
- Short interest (descriptive)

**Deliverable:** Holder Map populates in Brief. Insider activity is filtered and contextualized. No "smart money buy" language.

### Phase 5: Additional Sector Templates + Polish (Weeks 18-22)

- Banks template
- E&P template
- Healthcare / Biotech template (binary event-driven, pipeline-based)
- Industrials template
- Calibration tracking (thesis outcomes over time)
- Performance optimization, caching, mobile responsiveness

**Deliverable:** Production-grade tool covering 5-6 sector templates with calibration data accumulating.

---

## What This Is NOT

To keep the product honest and focused:

- **Not a screener.** No universal rankings by composite score. If a user wants to screen, they can filter by sector KPIs, but the output is always a Decision Brief per name, not a ranked list.
- **Not a dashboard with 50 metrics.** The Decision Brief shows what matters for this sector for this thesis. Everything else is available on drill-down but never on the default surface.
- **Not a chat-first product.** Chat is the controller. The Brief and Feed are the primary surfaces.
- **Not investment advice.** The tool provides evidence, structure, and monitoring. It never says "buy" or "sell." It says "here are the conditions under which your thesis holds or breaks."
- **Not a prediction engine.** No price targets, no probability of going up. Reverse DCF shows what's priced in. Claims show what you need to get right. Kill criteria show when you're wrong.
