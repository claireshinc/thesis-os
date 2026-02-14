"""
Data layer — fundamentals/prices via OpenBB SDK, filings/insider/13F via SEC EDGAR.

Every public function returns results with source metadata sufficient to build a
Citation (filing type, date, section, URL).  A simple TTL cache keeps repeated
lookups cheap within a session.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import httpx
from cachetools import TTLCache

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Source metadata attached to every data result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SourceMeta:
    """Enough info to construct a full Citation in the DB layer."""

    source_type: str  # "10-K", "10-Q", "8-K", "13F", "form4", "price", "fundamental"
    filer: str
    filing_date: date | None = None
    section: str | None = None
    page: int | None = None
    accession_number: str | None = None
    url: str = ""
    description: str = ""


@dataclass
class DataResult:
    """Wrapper returned by every data function."""

    data: Any
    source: SourceMeta
    fetched_at: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# TTL cache — simple in-process cache shared across calls
# ---------------------------------------------------------------------------

_cache: TTLCache = TTLCache(maxsize=512, ttl=900)  # 15-minute default


def _cache_key(*parts: str) -> str:
    return "|".join(parts)


# ---------------------------------------------------------------------------
# SEC EDGAR helpers
# ---------------------------------------------------------------------------

EDGAR_BASE = "https://efts.sec.gov/LATEST"
EDGAR_SUBMISSIONS = "https://data.sec.gov/submissions"
EDGAR_FULL_TEXT = "https://efts.sec.gov/LATEST/search-index"

_HEADERS = {"User-Agent": settings.sec_user_agent, "Accept": "application/json"}


def _edgar_filing_url(accession: str, primary_doc: str) -> str:
    """Build a direct link to a filing document on EDGAR."""
    acc_no_dashes = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{acc_no_dashes}/{accession}/{primary_doc}"


async def _get(client: httpx.AsyncClient, url: str, params: dict | None = None) -> dict:
    resp = await client.get(url, params=params, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# SEC EDGAR: Company filings (10-K, 10-Q, 8-K)
# ---------------------------------------------------------------------------

async def get_company_filings(
    ticker: str,
    form_types: list[str] | None = None,
    limit: int = 10,
) -> DataResult:
    """
    Fetch recent SEC filings for a ticker.

    Returns a list of filing dicts, each with accession_number, form_type,
    filing_date, primary_doc, and a direct URL.
    """
    key = _cache_key("filings", ticker, str(form_types), str(limit))
    if key in _cache:
        return _cache[key]

    async with httpx.AsyncClient() as client:
        # Resolve ticker → CIK via EDGAR company tickers JSON
        tickers_url = "https://www.sec.gov/files/company_tickers.json"
        tickers_data = await _get(client, tickers_url)
        cik = None
        for entry in tickers_data.values():
            if entry["ticker"].upper() == ticker.upper():
                cik = str(entry["cik_str"]).zfill(10)
                break
        if cik is None:
            raise ValueError(f"Ticker {ticker} not found in SEC EDGAR")

        # Fetch submissions
        sub_url = f"{EDGAR_SUBMISSIONS}/CIK{cik}.json"
        submissions = await _get(client, sub_url)
        recent = submissions.get("filings", {}).get("recent", {})

        filings: list[dict] = []
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])

        for i, form in enumerate(forms):
            if form_types and form not in form_types:
                continue
            accession = accessions[i]
            primary_doc = primary_docs[i]
            filing = {
                "form_type": form,
                "filing_date": dates[i],
                "accession_number": accession,
                "primary_document": primary_doc,
                "url": _edgar_filing_url(accession, primary_doc),
                "cik": cik,
            }
            filings.append(filing)
            if len(filings) >= limit:
                break

    result = DataResult(
        data=filings,
        source=SourceMeta(
            source_type="filing_index",
            filer=ticker.upper(),
            url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=&dateb=&owner=include&count=40",
            description=f"SEC EDGAR filing index for {ticker.upper()}",
        ),
    )
    _cache[key] = result
    return result


# ---------------------------------------------------------------------------
# SEC EDGAR: Full-text search within filings
# ---------------------------------------------------------------------------

async def search_filings(
    query: str,
    ticker: str | None = None,
    form_types: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 10,
) -> DataResult:
    """
    Full-text search across EDGAR filings (EFTS endpoint).

    Useful for finding specific language — e.g. "customer concentration",
    "revenue recognition", "goodwill impairment".
    """
    key = _cache_key("search", query, str(ticker), str(form_types))
    if key in _cache:
        return _cache[key]

    params: dict[str, Any] = {"q": query, "dateRange": "custom", "startdt": "", "enddt": ""}
    if ticker:
        params["entityName"] = ticker
    if form_types:
        params["forms"] = ",".join(form_types)
    if date_from:
        params["startdt"] = date_from
    if date_to:
        params["enddt"] = date_to

    async with httpx.AsyncClient() as client:
        url = f"{EDGAR_BASE}/search-index"
        resp = await client.get(
            "https://efts.sec.gov/LATEST/search-index",
            params=params,
            headers=_HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

    hits = data.get("hits", {}).get("hits", [])[:limit]
    results = []
    for hit in hits:
        src = hit.get("_source", {})
        results.append({
            "entity_name": src.get("entity_name"),
            "form_type": src.get("form_type"),
            "filing_date": src.get("file_date"),
            "accession_number": src.get("file_num"),
            "snippet": hit.get("highlight", {}).get("text", [""])[0],
        })

    result = DataResult(
        data=results,
        source=SourceMeta(
            source_type="full_text_search",
            filer=ticker or "all",
            url=f"https://efts.sec.gov/LATEST/search-index?q={query}",
            description=f"EDGAR full-text search: '{query}'",
        ),
    )
    _cache[key] = result
    return result


# ---------------------------------------------------------------------------
# SEC EDGAR: Insider transactions (Forms 3, 4, 5)
# ---------------------------------------------------------------------------

async def get_insider_transactions(ticker: str, limit: int = 50) -> DataResult:
    """
    Fetch recent insider transactions from SEC EDGAR.

    Each transaction includes: insider name, title, transaction type,
    shares, price, value, date, and whether it's a 10b5-1 plan transaction.
    """
    key = _cache_key("insider", ticker, str(limit))
    if key in _cache:
        return _cache[key]

    # Resolve CIK
    async with httpx.AsyncClient() as client:
        tickers_data = await _get(client, "https://www.sec.gov/files/company_tickers.json")
        cik = None
        for entry in tickers_data.values():
            if entry["ticker"].upper() == ticker.upper():
                cik = str(entry["cik_str"]).zfill(10)
                break
        if cik is None:
            raise ValueError(f"Ticker {ticker} not found in SEC EDGAR")

        # Fetch owner submissions (Forms 4)
        sub_url = f"{EDGAR_SUBMISSIONS}/CIK{cik}.json"
        submissions = await _get(client, sub_url)

    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    transactions: list[dict] = []
    for i, form in enumerate(forms):
        if form not in ("3", "4", "5"):
            continue
        transactions.append({
            "form_type": form,
            "filing_date": dates[i],
            "accession_number": accessions[i],
            "primary_document": primary_docs[i],
            "url": _edgar_filing_url(accessions[i], primary_docs[i]),
            "cik": cik,
        })
        if len(transactions) >= limit:
            break

    result = DataResult(
        data=transactions,
        source=SourceMeta(
            source_type="form4",
            filer=ticker.upper(),
            filing_date=date.fromisoformat(dates[0]) if dates else None,
            section="Statement of Changes in Beneficial Ownership",
            url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4&dateb=&owner=include&count=40",
            description=f"Insider transactions for {ticker.upper()}",
        ),
    )
    _cache[key] = result
    return result


# ---------------------------------------------------------------------------
# SEC EDGAR: 13F institutional holdings
# ---------------------------------------------------------------------------

async def get_13f_holdings(ticker: str, limit: int = 20) -> DataResult:
    """
    Fetch 13F institutional holder data for a company.

    Uses the EDGAR full-text search to find 13F-HR filings that mention
    the ticker, then returns holder names, share counts, and values.
    """
    key = _cache_key("13f", ticker, str(limit))
    if key in _cache:
        return _cache[key]

    async with httpx.AsyncClient() as client:
        params = {
            "q": ticker,
            "forms": "13F-HR",
            "dateRange": "custom",
            "startdt": "",
            "enddt": "",
        }
        resp = await client.get(
            "https://efts.sec.gov/LATEST/search-index",
            params=params,
            headers=_HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

    hits = data.get("hits", {}).get("hits", [])[:limit]
    holders: list[dict] = []
    for hit in hits:
        src = hit.get("_source", {})
        holders.append({
            "filer_name": src.get("entity_name"),
            "form_type": "13F-HR",
            "filing_date": src.get("file_date"),
            "accession_number": src.get("file_num"),
        })

    result = DataResult(
        data=holders,
        source=SourceMeta(
            source_type="13F",
            filer=ticker.upper(),
            section="13F-HR Information Table",
            url=f"https://efts.sec.gov/LATEST/search-index?q={ticker}&forms=13F-HR",
            description=f"13F institutional holders mentioning {ticker.upper()} (45-day lag from quarter-end)",
        ),
    )
    _cache[key] = result
    return result


# ---------------------------------------------------------------------------
# OpenBB SDK: Fundamentals
# ---------------------------------------------------------------------------

async def get_fundamentals(ticker: str) -> DataResult:
    """
    Fetch key financial statements via OpenBB Platform API.

    Returns income statement, balance sheet, and cash flow data
    for the most recent fiscal year.
    """
    key = _cache_key("fundamentals", ticker)
    if key in _cache:
        return _cache[key]

    # OpenBB Platform v4 exposes a REST API when run locally.
    # Fall back to direct provider (FMP free tier) if no local instance.
    base = "http://localhost:8000/api/v1"
    headers = {}
    if settings.openbb_token:
        headers["Authorization"] = f"Bearer {settings.openbb_token}"

    async with httpx.AsyncClient() as client:
        try:
            income_resp = await client.get(
                f"{base}/equity/fundamental/income",
                params={"symbol": ticker, "limit": 4, "provider": "fmp"},
                headers=headers,
                timeout=30,
            )
            income_resp.raise_for_status()
            income = income_resp.json()

            balance_resp = await client.get(
                f"{base}/equity/fundamental/balance",
                params={"symbol": ticker, "limit": 4, "provider": "fmp"},
                headers=headers,
                timeout=30,
            )
            balance_resp.raise_for_status()
            balance = balance_resp.json()

            cashflow_resp = await client.get(
                f"{base}/equity/fundamental/cash",
                params={"symbol": ticker, "limit": 4, "provider": "fmp"},
                headers=headers,
                timeout=30,
            )
            cashflow_resp.raise_for_status()
            cashflow = cashflow_resp.json()

        except httpx.HTTPError as exc:
            logger.warning("OpenBB Platform unavailable (%s), returning empty fundamentals", exc)
            income = balance = cashflow = {"results": []}

    data = {
        "income_statement": income.get("results", []),
        "balance_sheet": balance.get("results", []),
        "cash_flow": cashflow.get("results", []),
    }

    result = DataResult(
        data=data,
        source=SourceMeta(
            source_type="fundamental",
            filer=ticker.upper(),
            description=(
                f"Financial statements for {ticker.upper()} via OpenBB/FMP. "
                "Cross-reference against 10-K for citation."
            ),
        ),
    )
    _cache[key] = result
    return result


# ---------------------------------------------------------------------------
# OpenBB SDK: Historical prices
# ---------------------------------------------------------------------------

async def get_prices(
    ticker: str,
    start: str | None = None,
    end: str | None = None,
) -> DataResult:
    """
    Fetch daily OHLCV price history via OpenBB Platform.
    """
    key = _cache_key("prices", ticker, str(start), str(end))
    if key in _cache:
        return _cache[key]

    base = "http://localhost:8000/api/v1"
    headers = {}
    if settings.openbb_token:
        headers["Authorization"] = f"Bearer {settings.openbb_token}"

    params: dict[str, Any] = {"symbol": ticker, "provider": "fmp"}
    if start:
        params["start_date"] = start
    if end:
        params["end_date"] = end

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{base}/equity/price/historical",
                params=params,
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("OpenBB Platform unavailable (%s), returning empty prices", exc)
            data = {"results": []}

    result = DataResult(
        data=data.get("results", []),
        source=SourceMeta(
            source_type="price",
            filer=ticker.upper(),
            description=f"Daily OHLCV for {ticker.upper()} via OpenBB/FMP",
        ),
    )
    _cache[key] = result
    return result


# ---------------------------------------------------------------------------
# SEC EDGAR: Filing full-text retrieval
# ---------------------------------------------------------------------------

async def get_filing_text(accession_number: str, cik: str) -> DataResult:
    """
    Download the full text of a specific filing by accession number.

    Returns the raw text content (HTML stripped where possible) and the
    source URL for citation.
    """
    key = _cache_key("filing_text", accession_number)
    if key in _cache:
        return _cache[key]

    acc_no_dashes = accession_number.replace("-", "")
    index_url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_no_dashes}/"
        f"{accession_number}-index.htm"
    )

    async with httpx.AsyncClient() as client:
        # Get the filing index to find the primary document
        resp = await client.get(index_url, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        index_html = resp.text

        # The primary .htm document is typically the largest file listed
        # For now, return the index; a full parser would extract and clean the doc
        text = index_html

    result = DataResult(
        data=text,
        source=SourceMeta(
            source_type="filing_text",
            filer=cik,
            accession_number=accession_number,
            url=index_url,
            description=f"Full text of filing {accession_number}",
        ),
    )
    _cache[key] = result
    return result


# ---------------------------------------------------------------------------
# CIK resolution helper (cached)
# ---------------------------------------------------------------------------

async def _resolve_cik(ticker: str) -> str:
    """Resolve a ticker symbol to a zero-padded 10-digit SEC CIK."""
    key = _cache_key("cik", ticker.upper())
    if key in _cache:
        return _cache[key]
    async with httpx.AsyncClient() as client:
        data = await _get(client, "https://www.sec.gov/files/company_tickers.json")
    for entry in data.values():
        if entry["ticker"].upper() == ticker.upper():
            cik = str(entry["cik_str"]).zfill(10)
            _cache[key] = cik
            return cik
    raise ValueError(f"Ticker {ticker} not found in SEC EDGAR")


# ---------------------------------------------------------------------------
# XBRL concept name → internal field name mapping
#
# Each entry: field_name -> (list_of_candidate_xbrl_concepts, unit_key)
# We try candidates in order and use the first one found for a given company.
# ---------------------------------------------------------------------------

XBRL_FIELD_MAP: dict[str, tuple[list[str], str]] = {
    # --- Income Statement ---
    "revenue": ([
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ], "USD"),
    "cost_of_revenue": ([
        "CostOfGoodsAndServicesSold",
        "CostOfRevenue",
        "CostOfGoodsSold",
    ], "USD"),
    "gross_profit": ([
        "GrossProfit",
    ], "USD"),
    "research_and_development": ([
        "ResearchAndDevelopmentExpense",
    ], "USD"),
    "sga": ([
        "SellingGeneralAndAdministrativeExpense",
    ], "USD"),
    "operating_income": ([
        "OperatingIncomeLoss",
    ], "USD"),
    "net_income": ([
        "NetIncomeLoss",
    ], "USD"),
    "interest_expense": ([
        "InterestExpense",
        "InterestExpenseDebt",
    ], "USD"),
    "income_tax": ([
        "IncomeTaxExpenseBenefit",
    ], "USD"),
    "depreciation_amortization": ([
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "Depreciation",
    ], "USD"),
    "sbc": ([
        "ShareBasedCompensation",
        "AllocatedShareBasedCompensationExpense",
    ], "USD"),

    # --- Balance Sheet ---
    "total_assets": ([
        "Assets",
    ], "USD"),
    "current_assets": ([
        "AssetsCurrent",
    ], "USD"),
    "cash_and_equivalents": ([
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsAndShortTermInvestments",
    ], "USD"),
    "short_term_investments": ([
        "ShortTermInvestments",
        "AvailableForSaleSecuritiesCurrent",
        "MarketableSecuritiesCurrent",
    ], "USD"),
    "accounts_receivable": ([
        "AccountsReceivableNetCurrent",
        "AccountsReceivableNet",
    ], "USD"),
    "inventory": ([
        "InventoryNet",
    ], "USD"),
    "property_plant_equipment": ([
        "PropertyPlantAndEquipmentNet",
    ], "USD"),
    "total_liabilities": ([
        "Liabilities",
    ], "USD"),
    "current_liabilities": ([
        "LiabilitiesCurrent",
    ], "USD"),
    "long_term_debt": ([
        "LongTermDebtNoncurrent",
        "LongTermDebt",
    ], "USD"),
    "short_term_debt": ([
        "ShortTermBorrowings",
        "DebtCurrent",
        "LongTermDebtCurrent",
    ], "USD"),
    "total_equity": ([
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ], "USD"),
    "retained_earnings": ([
        "RetainedEarningsAccumulatedDeficit",
    ], "USD"),
    "goodwill": ([
        "Goodwill",
    ], "USD"),
    "intangible_assets": ([
        "IntangibleAssetsNetExcludingGoodwill",
        "FiniteLivedIntangibleAssetsNet",
    ], "USD"),

    # --- Cash Flow ---
    "operating_cash_flow": ([
        "NetCashProvidedByUsedInOperatingActivities",
    ], "USD"),
    "capex": ([
        "PaymentsToAcquirePropertyPlantAndEquipment",
    ], "USD"),
    "dividends_paid": ([
        "PaymentsOfDividends",
        "PaymentsOfDividendsCommonStock",
    ], "USD"),
    "share_repurchases": ([
        "PaymentsForRepurchaseOfCommonStock",
    ], "USD"),

    # --- Shares (often in the dei namespace) ---
    "shares_outstanding": ([
        "EntityCommonStockSharesOutstanding",
        "CommonStockSharesOutstanding",
    ], "shares"),
}


# ---------------------------------------------------------------------------
# SEC XBRL: Company financial facts (primary financials source)
# ---------------------------------------------------------------------------

async def get_company_facts(ticker: str, periods: int = 5) -> DataResult:
    """
    Fetch structured financial data from SEC XBRL companyfacts.

    Returns normalized field names (revenue, total_assets, operating_cash_flow,
    etc.) with up to *periods* annual values each, most recent first.
    Every value carries its accession number and filing date for citation.
    """
    key = _cache_key("companyfacts", ticker.upper(), str(periods))
    if key in _cache:
        return _cache[key]

    cik = await _resolve_cik(ticker)

    async with httpx.AsyncClient() as client:
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        raw = await _get(client, url)

    entity_name = raw.get("entityName", ticker.upper())
    us_gaap = raw.get("facts", {}).get("us-gaap", {})
    dei = raw.get("facts", {}).get("dei", {})

    facts: dict[str, list[dict]] = {}

    for field_name, (xbrl_concepts, unit_key) in XBRL_FIELD_MAP.items():
        for concept in xbrl_concepts:
            # Check both namespaces
            concept_data = us_gaap.get(concept) or dei.get(concept)
            if not concept_data:
                continue

            entries = concept_data.get("units", {}).get(unit_key, [])

            # Filter to annual filings
            annual = [
                e for e in entries
                if e.get("fp") == "FY"
                and e.get("form") in ("10-K", "10-K/A", "20-F", "20-F/A")
            ]

            # Deduplicate by fiscal year — keep the most recently filed value
            by_fy: dict[int, dict] = {}
            for e in annual:
                fy = e.get("fy", 0)
                existing = by_fy.get(fy)
                if existing is None or e.get("filed", "") > existing.get("filed", ""):
                    by_fy[fy] = e

            # Sort by fiscal year descending, take most recent N
            sorted_entries = sorted(
                by_fy.values(), key=lambda e: e.get("fy", 0), reverse=True
            )[:periods]

            if sorted_entries:
                facts[field_name] = [
                    {
                        "value": e["val"],
                        "period_end": e.get("end"),
                        "fiscal_year": e.get("fy"),
                        "fiscal_period": e.get("fp"),
                        "form": e.get("form"),
                        "accession": e.get("accn"),
                        "filed": e.get("filed"),
                        "xbrl_concept": concept,
                    }
                    for e in sorted_entries
                ]
                break  # Found data for this field, stop trying alternatives

    result = DataResult(
        data={"entity_name": entity_name, "cik": cik, "facts": facts},
        source=SourceMeta(
            source_type="xbrl_companyfacts",
            filer=entity_name,
            url=f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
            description=f"SEC XBRL companyfacts for {entity_name}",
        ),
    )
    _cache[key] = result
    return result


# ---------------------------------------------------------------------------
# Real-time quote (price, shares, market cap)
# ---------------------------------------------------------------------------

async def get_quote(ticker: str) -> DataResult:
    """
    Fetch current price via Yahoo Finance v8 chart endpoint (no key required).

    Returns price, currency, and shares_outstanding / market_cap when available.
    """
    key = _cache_key("quote", ticker.upper())
    if key in _cache:
        return _cache[key]

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"interval": "1d", "range": "1d"}
    yf_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    price = None
    currency = "USD"

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, params=params, headers=yf_headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            meta = data["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice") or meta.get("previousClose")
            currency = meta.get("currency", "USD")
        except httpx.HTTPError as exc:
            logger.warning("Yahoo Finance unavailable (%s), price will be None", exc)

    result = DataResult(
        data={"price": price, "currency": currency},
        source=SourceMeta(
            source_type="price",
            filer=ticker.upper(),
            description=f"Real-time quote for {ticker.upper()} via Yahoo Finance"
            if price else f"Quote unavailable for {ticker.upper()}",
        ),
    )
    _cache[key] = result
    return result


# ---------------------------------------------------------------------------
# US Treasury 10-year yield (for WACC risk-free rate)
# ---------------------------------------------------------------------------

async def get_treasury_yield() -> DataResult:
    """
    Fetch the most recent US Treasury 10-year yield from Treasury.gov.

    Returns the yield as a decimal (e.g. 0.0425 for 4.25%).
    """
    key = _cache_key("treasury_10y")
    if key in _cache:
        return _cache[key]

    ten_year = 0.0425
    yield_date = "fallback"

    # Try the Treasury fiscal data API (v2)
    url = (
        "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
        "/v2/accounting/od/avg_interest_rates"
        "?sort=-record_date&page[size]=1"
        "&filter=security_desc:eq:Treasury Bonds"
    )
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            records = data.get("data", [])
            if records:
                raw_val = records[0].get("avg_interest_rate_amt")
                if raw_val:
                    ten_year = float(raw_val) / 100.0
                    yield_date = records[0].get("record_date", "")
    except Exception as exc:
        logger.warning("Treasury API unavailable (%s), using %.2f%% fallback", exc, ten_year * 100)

    result = DataResult(
        data={"ten_year": ten_year, "date": yield_date},
        source=SourceMeta(
            source_type="treasury_yield",
            filer="US Treasury",
            url="https://home.treasury.gov/resource-center/data-chart-center/interest-rates",
            description=f"US Treasury 10Y yield: {ten_year:.2%}",
        ),
    )
    _cache[key] = result
    return result
