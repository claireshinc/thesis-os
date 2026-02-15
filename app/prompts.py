"""
LLM prompt constants for the qualitative engine.

Every prompt enforces two invariants:
  1. Cite section name (and page if verifiable) for every claim.
  2. Label each output as "fact" or "interpretation".
"""

# ---------------------------------------------------------------------------
# Shared citation rules injected into every prompt
# ---------------------------------------------------------------------------

CITATION_RULES = """
CITATION RULES (MANDATORY — violations invalidate your entire response):

1. Every factual claim must include the exact SECTION NAME from the filing
   (e.g., "Risk Factors", "Management's Discussion and Analysis",
   "Revenue Recognition", "Note 12 — Debt").

2. PAGE NUMBERS:
   - If you can confidently identify the page from context clues (page headers,
     explicit page references in the text, table of contents), include it.
   - If you CANNOT verify the page number, set "page": null and include
     "page_unverified": true.
   - NEVER guess or fabricate a page number. An omitted page is always
     preferable to an invented one.

3. Include a brief QUOTE or close paraphrase from the filing (under 100 words).
   Put exact quotes in quotation marks.

4. FACT vs INTERPRETATION — label every piece of output:
   - "fact": directly stated in the filing, verifiable by reading the section.
   - "interpretation": your inference from what's stated. Must be explicitly
     labeled so the PM knows it's editorial.
""".strip()


# ---------------------------------------------------------------------------
# Evidence builder — supporting + disconfirming evidence for user's claims
# ---------------------------------------------------------------------------

EVIDENCE_BUILDER_PROMPT = """You are a research associate at a fundamental equity fund.
Your job is to find evidence in SEC filings — both supporting AND disconfirming.
You are NOT making investment recommendations. You are gathering cited evidence.

{citation_rules}

ADDITIONAL RULES:
- Actively look for disconfirming evidence. Your job is to be balanced, not to
  support the thesis.
- If you cannot find evidence for a claim in this filing, respond with
  "No direct evidence found in this filing" — do NOT fabricate or stretch.
- Do not editorialize beyond what's asked. No buy/sell language.

Ticker: {ticker}
Filing: {form_type} filed {filing_date} (accession: {accession_number})

Claims to evaluate:
{claims_json}

Respond in JSON (no markdown fences, just raw JSON):
{{
  "claim_evidence": [
    {{
      "claim_id": "...",
      "supporting": [
        {{
          "content": "What the filing says (brief quote or paraphrase)",
          "section": "Exact section name from filing",
          "page": null,
          "page_unverified": true,
          "type": "fact"
        }},
        {{
          "content": "What this might imply for the claim",
          "section": "Same section",
          "page": null,
          "page_unverified": true,
          "type": "interpretation"
        }}
      ],
      "disconfirming": [
        {{
          "content": "...",
          "section": "...",
          "page": null,
          "page_unverified": true,
          "type": "fact"
        }}
      ],
      "evidence_strength": "strong|moderate|weak|none",
      "summary": "One sentence: how this filing relates to the claim"
    }}
  ]
}}

Filing text:
{filing_text}
""".strip()


# ---------------------------------------------------------------------------
# Red flag detector — sector-aware
# ---------------------------------------------------------------------------

RED_FLAG_PROMPT = """You are an auditor reviewing a {sector_name} company's filing
for potential red flags. You are thorough but not alarmist — flag only what you
can cite directly from the filing.

{citation_rules}

HEADLINE RULE (MANDATORY):
Every red flag headline in the "flag" field MUST contain:
  1. The specific metric name
  2. The actual values for the last 2 periods
  3. The computed % change
Example headline: "CapEx grew 43% YoY ($32.3B vs $22.6B) while revenue grew 14%"
Example headline: "SBC/Revenue ratio rose to 12.3% from 10.1% (+220bps YoY)"
Example headline: "Accounts receivable grew 28% ($8.2B vs $6.4B) outpacing revenue growth of 14%"
NEVER write vague headlines like "potential risk from infrastructure investments"
or "increasing compensation expense". If you cannot cite specific numbers from
the filing, do NOT include the flag.

SECTOR-SPECIFIC RED FLAGS TO CHECK:
{sector_checklist}

UNIVERSAL RED FLAGS (check these for every sector):
- Revenue recognition policy changes
- Growing gap between GAAP and non-GAAP earnings
- Related party transactions
- Auditor changes or going concern language
- Material weakness in internal controls
- Unusual increase in "other" income/expense
- Receivables growing faster than revenue (DSO expansion)
- Changes in accounting estimates (useful life, reserves, assumptions)
- Significant off-balance-sheet arrangements

Ticker: {ticker}
Filing: {form_type} filed {filing_date}

For each red flag found, respond in JSON (no markdown fences):
{{
  "red_flags": [
    {{
      "flag": "Specific headline with metric name, values, and % change (see HEADLINE RULE)",
      "severity": "high|medium|low",
      "section": "Exact filing section name",
      "page": null,
      "page_unverified": true,
      "evidence": "What specifically in the filing triggered this flag (quote or paraphrase with exact numbers)",
      "context": "Why this matters or why it might be benign — include sector context",
      "type": "fact"
    }}
  ],
  "clean_areas": ["List of checked areas where no red flags were found"]
}}

If no red flags are found, return {{"red_flags": [], "clean_areas": [...]}}.
Only flag things you can cite directly from the filing with specific numbers.

Filing text:
{filing_text}
""".strip()


# ---------------------------------------------------------------------------
# Sector-specific red flag checklists (inserted into RED_FLAG_PROMPT)
# ---------------------------------------------------------------------------

SECTOR_RED_FLAG_CHECKLISTS: dict[str, str] = {
    "saas": """
- SBC as % of revenue increasing while growth decelerates
- Capitalized software development costs growing faster than revenue
- Deferred revenue declining while reported revenue grows (pull-forward risk)
- Customer concentration: any single customer >10% of revenue
- Remaining Performance Obligations (RPO) declining or growing slower than revenue
- Billings growth diverging significantly from revenue growth
- Non-GAAP adjustments becoming more aggressive over time
- Change in revenue recognition methodology or ASC 606 adoption impacts
""".strip(),

    "semis": """
- Inventory build-up outpacing revenue growth (channel stuffing risk)
- Gross margin declining faster than revenue (pricing pressure or mix deterioration)
- Customer concentration in cyclical end-markets
- Capitalized development costs or mask/tooling costs growing disproportionately
- Warranty reserves declining as a % of revenue (under-reserving)
- Geographic revenue concentration shifting (export control risk)
- Long-lived asset impairments or goodwill write-downs
- Backlog cancellation language or "right to cancel" clauses
""".strip(),

    "banks": """
- Allowance for credit losses declining as a % of total loans
- Non-performing assets rising while provision expense stays flat
- Held-to-maturity securities portfolio with large unrealized losses
- CET1 ratio declining toward regulatory minimums
- Net interest margin compression without offsetting fee income growth
- Rapid loan growth in riskier categories (CRE, leveraged lending)
- Off-balance-sheet exposure growth (commitments, derivatives notional)
- Changes in CECL methodology or assumptions
""".strip(),

    "e_and_p": """
- Reserve replacement ratio below 100% for multiple years
- Finding & development costs rising faster than commodity prices
- Proved undeveloped reserves (PUDs) not being converted to proved developed
- Hedging book covering declining percentage of production
- Asset retirement obligations growing relative to producing asset base
- Full-cost ceiling test write-downs (or approaching threshold)
- Related party transactions with midstream/services affiliates
- Production decline rates accelerating
""".strip(),
}


# ---------------------------------------------------------------------------
# Targeted filing query — find specific language
# ---------------------------------------------------------------------------

FILING_QUERY_PROMPT = """Find the exact language in this SEC filing that addresses
the following query. Return the filing's own words — do not paraphrase or interpret
unless no exact passage exists.

{citation_rules}

Ticker: {ticker}
Filing: {form_type} filed {filing_date}
Query: "{query}"

Respond in JSON (no markdown fences):
{{
  "passages": [
    {{
      "excerpt": "Exact or near-exact quote from filing (keep under 200 words)",
      "section": "Section name where this appears",
      "page": null,
      "page_unverified": true,
      "relevance": "Brief note on why this passage answers the query",
      "type": "fact"
    }}
  ],
  "query_answered": true
}}

Return 1-5 relevant passages, ordered by relevance. If nothing relevant is found,
return {{"passages": [], "query_answered": false}}.

Filing text:
{filing_text}
""".strip()


# ---------------------------------------------------------------------------
# Structured KPI extraction — extract specific metrics from filing text
# ---------------------------------------------------------------------------

STRUCTURED_KPI_EXTRACTION_PROMPT = """You are a financial data extraction specialist.
Your job is to extract SPECIFIC numeric KPIs from an SEC filing. Only extract values
that are explicitly stated — NEVER estimate, compute, or infer values.

Ticker: {ticker}
Filing: {form_type} filed {filing_date}

KPIs to extract:
{kpi_requests}

For EACH requested KPI, respond in JSON (no markdown fences):
{{
  "extracted_kpis": [
    {{
      "kpi_id": "the_requested_kpi_id",
      "value": 115.0,
      "unit": "%",
      "period": "FY2025",
      "exact_quote": "The exact sentence from the filing containing this number",
      "section": "Section name where found",
      "confidence": "high|medium|low",
      "note": "Any relevant context (e.g., 'reported as dollar-based net retention')"
    }}
  ]
}}

Rules:
- ONLY extract values explicitly stated in the filing. If a KPI is not disclosed,
  omit it from the response entirely — do NOT guess or approximate.
- "high" confidence: exact number clearly labeled in the filing.
- "medium" confidence: number is stated but label is slightly different from requested KPI.
- "low" confidence: number requires interpretation (e.g., computing from two stated values).
- Include the EXACT QUOTE containing the number (under 100 words).
- If the company uses a different name for the same metric (e.g., "dollar-based net
  expansion rate" instead of "net revenue retention"), extract it and note the alias.

Filing text:
{filing_text}
""".strip()
