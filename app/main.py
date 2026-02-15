"""
FastAPI application — Thesis OS API.

Routes:
  GET    /health                     — liveness check
  GET    /brief/{ticker}             — generate a full Decision Brief
  POST   /command                    — dispatch a command (/thesis, /stress, /filing, /evidence)
  POST   /chat                       — alias for /command
  POST   /thesis/{ticker}            — compile + persist a thesis
  GET    /thesis/{thesis_id}         — fetch a saved thesis
  GET    /theses                     — list theses (filter by ticker, status)
  PATCH  /thesis/{thesis_id}/lock    — transition draft → monitoring
  PATCH  /thesis/{thesis_id}/close   — close a thesis with reason
  POST   /stress/{ticker}            — stress test a thesis or memo
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.brief import DecisionBriefResponse, detect_sector, generate_brief
from app.coverage import DriverCoverageResponse, compute_coverage_from_claims
from app.data import get_company_submissions
from app.changes import ChangeFeedResponse, detect_changes
from app.db import get_session, init_db
from app.export import export_brief_markdown, export_brief_pdf, export_thesis_markdown
from app.extraction import supplement_kpis_from_filings
from app.quant import QuantEngine
from app.templates import SECTOR_TEMPLATES, get_template
from app.thesis import CommandRouter, ThesisCompiler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


# ───────────────────────────────────────────────────────────────────────────
# App lifecycle
# ───────────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Thesis OS",
    description="Decision artifact engine for fundamental equity PMs.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ───────────────────────────────────────────────────────────────────────────
# Pydantic response models — thesis CRUD
# ───────────────────────────────────────────────────────────────────────────


class ClaimResponse(BaseModel):
    id: str
    statement: str
    kpi_id: str
    kpi_family: str = "lagging"
    current_value: float | None = None
    qoq_delta: float | None = None
    yoy_delta: float | None = None
    status: str

    model_config = {"from_attributes": True}


class KillCriterionResponse(BaseModel):
    id: str
    description: str
    metric: str
    operator: str
    threshold: float
    duration: str | None = None
    current_value: float | None = None
    status: str
    distance_pct: float | None = None
    watch_reason: str | None = None

    model_config = {"from_attributes": True}


class CatalystResponse(BaseModel):
    id: int
    ticker: str
    event_date: date
    event: str
    claims_tested: list[str] | None = None
    kill_criteria_tested: list[str] | None = None
    occurred: bool
    outcome_notes: str | None = None

    model_config = {"from_attributes": True}


class ThesisResponse(BaseModel):
    id: uuid.UUID
    ticker: str
    direction: str
    thesis_text: str
    sector_template: str
    status: str
    variant: str | None = None
    mechanism: str | None = None
    disconfirming: list[str] | None = None
    driver_coverage: DriverCoverageResponse | None = None
    entry_price: float | None = None
    entry_date: date | None = None
    close_price: float | None = None
    close_date: date | None = None
    close_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    claims: list[ClaimResponse] = []
    kill_criteria: list[KillCriterionResponse] = []
    catalysts: list[CatalystResponse] = []

    model_config = {"from_attributes": True}


class ThesisListItem(BaseModel):
    id: uuid.UUID
    ticker: str
    direction: str
    status: str
    sector_template: str
    thesis_text: str
    entry_price: float | None = None
    entry_date: date | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ThesisListResponse(BaseModel):
    theses: list[ThesisListItem]
    count: int


# ───────────────────────────────────────────────────────────────────────────
# Health check
# ───────────────────────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "available_sectors": list(SECTOR_TEMPLATES.keys()),
    }


# ───────────────────────────────────────────────────────────────────────────
# Decision Brief
# ───────────────────────────────────────────────────────────────────────────


@app.get(
    "/brief/{ticker}",
    response_model=DecisionBriefResponse,
    summary="Generate a Decision Brief for a ticker",
    responses={
        400: {"description": "Invalid ticker or no sector template mapped"},
        502: {"description": "Upstream data source failure"},
    },
)
async def get_brief(
    ticker: str,
    sector: str | None = Query(
        default=None,
        description=(
            "Override auto-detected sector template. "
            f"Options: {', '.join(sorted(SECTOR_TEMPLATES.keys()))}"
        ),
    ),
) -> DecisionBriefResponse:
    """
    Generate a full Decision Brief for the given ticker.

    Auto-detects the sector template from SIC code unless `?sector=` is
    provided.  Runs quant, flow, and qualitative engines in parallel.
    """
    if sector and sector not in SECTOR_TEMPLATES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown sector '{sector}'. "
                f"Available: {', '.join(sorted(SECTOR_TEMPLATES.keys()))}"
            ),
        )

    try:
        return await generate_brief(ticker, sector_override=sector)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logging.getLogger(__name__).error("Brief generation failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to generate brief for {ticker.upper()}: {exc}",
        )


# ───────────────────────────────────────────────────────────────────────────
# Command router — natural language command dispatch
# ───────────────────────────────────────────────────────────────────────────

_router = CommandRouter()


class CommandRequest(BaseModel):
    command: str = Field(
        ...,
        description='Command string, e.g. "/thesis AAPL long — Services revenue will..."',
        examples=[
            "/thesis AAPL long — Apple's services revenue will grow 20% driven by...",
            "/stress NVDA — Datacenter GPU demand is sustainable because...",
            "/filing CRM customer concentration",
            "/brief AAPL",
        ],
    )


class CommandResponse(BaseModel):
    command: str
    result: dict | None = None
    error: str | None = None


@app.post(
    "/command",
    response_model=CommandResponse,
    summary="Dispatch a command",
)
async def dispatch_command(req: CommandRequest) -> CommandResponse:
    """
    Parse and dispatch a slash command.

    Supported: /thesis, /stress, /filing, /evidence, /brief
    """
    result = await _router.dispatch(req.command)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return CommandResponse(**result)


@app.post(
    "/chat",
    response_model=CommandResponse,
    summary="Dispatch a command (alias for /command)",
)
async def chat(req: CommandRequest) -> CommandResponse:
    """Alias for /command — used by the chat UI."""
    return await dispatch_command(req)


# ───────────────────────────────────────────────────────────────────────────
# Thesis compiler — compile + persist
# ───────────────────────────────────────────────────────────────────────────


class ThesisRequest(BaseModel):
    direction: str = Field(..., description="long or short", pattern="^(long|short)$")
    thesis_text: str = Field(..., description="Plain-English thesis statement")
    sector: str | None = Field(default=None, description="Sector override")
    entry_price: float | None = Field(default=None, description="Entry price if known")


@app.post(
    "/thesis/{ticker}",
    response_model=ThesisResponse,
    summary="Compile a thesis into structured claims + kill criteria and persist",
    responses={
        400: {"description": "Invalid ticker, direction, or missing API key"},
        502: {"description": "Upstream data source or LLM failure"},
    },
)
async def compile_thesis(
    ticker: str,
    req: ThesisRequest,
    session: AsyncSession = Depends(get_session),
) -> ThesisResponse:
    """
    Decompose a plain-English thesis into structured claims, kill criteria,
    and catalysts.  Populates current KPI values from the quant engine.
    Persists the result to the database and returns the saved thesis with ID.
    """
    ticker = ticker.upper()

    # 1. Detect sector
    if req.sector:
        if req.sector not in SECTOR_TEMPLATES:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown sector '{req.sector}'. Available: {', '.join(sorted(SECTOR_TEMPLATES.keys()))}",
            )
        template = get_template(req.sector)
    else:
        _, template, _ = await detect_sector(ticker)

    # 2. Run quant engine for KPI values + market-implied context
    quant_engine = QuantEngine()
    try:
        quant_output = await quant_engine.analyze(ticker, template)
    except Exception as exc:
        logging.getLogger(__name__).error("Quant engine failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"Quant engine failed: {exc}")

    # 2b. Supplement KPIs from filing text
    sub_result = await get_company_submissions(ticker)
    cik = sub_result.data["cik"] if not req.sector else sub_result.data.get("cik", "")
    try:
        quant_output = await supplement_kpis_from_filings(
            ticker, template, quant_output, cik,
        )
    except Exception as exc:
        logging.getLogger(__name__).warning("KPI supplement failed: %s", exc)

    # 3. Compile thesis (LLM call)
    try:
        compiler = ThesisCompiler()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        draft = await compiler.compile(
            ticker, req.direction, req.thesis_text, quant_output, template,
        )
    except Exception as exc:
        logging.getLogger(__name__).error("Thesis compilation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"Thesis compilation failed: {exc}")

    # 4. Persist to DB
    thesis = await crud.save_thesis(session, draft, entry_price=req.entry_price)
    await session.commit()

    # 5. Reload with relationships for response
    thesis = await crud.get_thesis(session, thesis.id)
    resp = ThesisResponse.model_validate(thesis)
    resp.driver_coverage = compute_coverage_from_claims(thesis.claims)
    return resp


# ───────────────────────────────────────────────────────────────────────────
# Thesis CRUD — fetch, list, lock, close
# ───────────────────────────────────────────────────────────────────────────


@app.get(
    "/thesis/{thesis_id}",
    response_model=ThesisResponse,
    summary="Fetch a saved thesis with claims, kill criteria, catalysts",
    responses={404: {"description": "Thesis not found"}},
)
async def get_thesis_by_id(
    thesis_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ThesisResponse:
    """Fetch a persisted thesis by its UUID."""
    thesis = await crud.get_thesis(session, thesis_id)
    if thesis is None:
        raise HTTPException(status_code=404, detail=f"Thesis {thesis_id} not found")
    resp = ThesisResponse.model_validate(thesis)
    resp.driver_coverage = compute_coverage_from_claims(thesis.claims)
    return resp


@app.get(
    "/theses",
    response_model=ThesisListResponse,
    summary="List theses with optional filters",
)
async def list_theses(
    ticker: str | None = Query(default=None, description="Filter by ticker"),
    status: str | None = Query(default=None, description="Filter by status (draft, monitoring, closed, killed)"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> ThesisListResponse:
    """List theses, optionally filtered by ticker and/or status."""
    theses = await crud.list_theses(
        session, ticker=ticker, status=status, limit=limit, offset=offset,
    )
    return ThesisListResponse(
        theses=[ThesisListItem.model_validate(t) for t in theses],
        count=len(theses),
    )


class LockRequest(BaseModel):
    entry_price: float | None = Field(default=None, description="Entry price")


@app.patch(
    "/thesis/{thesis_id}/lock",
    response_model=ThesisResponse,
    summary="Lock a thesis — transition from draft to monitoring",
    responses={
        400: {"description": "Thesis not in draft status"},
        404: {"description": "Thesis not found"},
    },
)
async def lock_thesis(
    thesis_id: uuid.UUID,
    req: LockRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> ThesisResponse:
    """Lock a draft thesis to begin monitoring."""
    try:
        entry_price = req.entry_price if req else None
        await crud.lock_thesis(session, thesis_id, entry_price=entry_price)
        await session.commit()
        thesis = await crud.get_thesis(session, thesis_id)
        return ThesisResponse.model_validate(thesis)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class CloseRequest(BaseModel):
    reason: str = Field(..., description="Why the thesis is being closed")
    close_price: float | None = Field(default=None, description="Close/exit price")


@app.patch(
    "/thesis/{thesis_id}/close",
    response_model=ThesisResponse,
    summary="Close a thesis with a reason",
    responses={
        400: {"description": "Thesis already closed or invalid state"},
        404: {"description": "Thesis not found"},
    },
)
async def close_thesis(
    thesis_id: uuid.UUID,
    req: CloseRequest,
    session: AsyncSession = Depends(get_session),
) -> ThesisResponse:
    """Close a thesis — record the reason and optionally the exit price."""
    try:
        await crud.close_thesis(
            session, thesis_id, reason=req.reason, close_price=req.close_price,
        )
        await session.commit()
        thesis = await crud.get_thesis(session, thesis_id)
        return ThesisResponse.model_validate(thesis)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ───────────────────────────────────────────────────────────────────────────
# Stress test — structured endpoint
# ───────────────────────────────────────────────────────────────────────────


class StressRequest(BaseModel):
    memo_text: str = Field(..., description="Memo bullets or thesis text to stress-test")


@app.post(
    "/stress/{ticker}",
    summary="Adversarial stress test of a thesis or memo",
)
async def stress_test(ticker: str, req: StressRequest) -> dict:
    """
    Run adversarial analysis: circular reasoning, priced-in check,
    falsification tests, missing disconfirming evidence, PM questions.
    """
    result = await _router.dispatch(
        f"/stress {ticker} — {req.memo_text}"
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result["result"]


# ───────────────────────────────────────────────────────────────────────────
# Export — markdown and PDF
# ───────────────────────────────────────────────────────────────────────────


@app.get(
    "/export/brief/{ticker}",
    summary="Export a Decision Brief as markdown or PDF",
    responses={
        400: {"description": "Invalid ticker, sector, or format"},
        502: {"description": "Upstream data source failure"},
    },
)
async def export_brief(
    ticker: str,
    format: str = Query(default="md", description="Export format: md or pdf"),
    sector: str | None = Query(default=None, description="Sector override"),
) -> Response:
    """Export a Decision Brief as markdown (default) or PDF."""
    if format not in ("md", "pdf"):
        raise HTTPException(status_code=400, detail="format must be 'md' or 'pdf'")

    try:
        if format == "pdf":
            pdf_bytes = await export_brief_pdf(ticker, sector_override=sector)
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{ticker.upper()}_brief.pdf"'},
            )
        else:
            md = await export_brief_markdown(ticker, sector_override=sector)
            return Response(
                content=md,
                media_type="text/markdown; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{ticker.upper()}_brief.md"'},
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logging.getLogger(__name__).error("Export failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"Export failed for {ticker.upper()}: {exc}")


@app.get(
    "/export/thesis/{thesis_id}",
    summary="Export a saved thesis as markdown",
    responses={
        404: {"description": "Thesis not found"},
    },
)
async def export_thesis(
    thesis_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Export a persisted thesis as markdown."""
    try:
        md = await export_thesis_markdown(thesis_id, session)
        return Response(
            content=md,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="thesis_{thesis_id}.md"'},
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ───────────────────────────────────────────────────────────────────────────
# Change feed — what changed since a date
# ───────────────────────────────────────────────────────────────────────────


@app.get(
    "/feed/{ticker}",
    response_model=ChangeFeedResponse,
    summary="What changed since a given date",
    responses={
        400: {"description": "Invalid date format"},
        502: {"description": "Upstream data source failure"},
    },
)
async def change_feed(
    ticker: str,
    since: str = Query(..., description="ISO date string, e.g. 2026-01-01"),
    session: AsyncSession = Depends(get_session),
) -> ChangeFeedResponse:
    """
    On-demand change detection: new SEC filings, insider transactions,
    and KPI threshold proximity since the given date.
    """
    try:
        since_date = date.fromisoformat(since)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format: '{since}'. Use YYYY-MM-DD.",
        )

    try:
        return await detect_changes(ticker, since_date, session=session)
    except Exception as exc:
        logging.getLogger(__name__).error("Change feed failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=str(exc))
