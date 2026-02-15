# Thesis OS

Decision artifacts for fundamental equity PMs. Generates structured briefs, compiles investment theses into testable claims with kill criteria, and monitors them over time.

## Prerequisites

- Python 3.11+
- Node.js 18+
- Docker (for Postgres)
- [uv](https://docs.astral.sh/uv/) (Python package manager)

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url> && cd thesis-os

# Python deps
uv sync

# Frontend deps
cd frontend && npm install && cd ..
```

### 2. Configure environment

Copy the example and fill in your keys:

```bash
cp .env.example .env
```

Required variables in `.env`:

| Variable | Required | Description |
|----------|----------|-------------|
| `POSTGRES_USER` | Yes | Postgres username (default: `thesis`) |
| `POSTGRES_PASSWORD` | Yes | Postgres password (default: `thesis`) |
| `POSTGRES_DB` | Yes | Database name (default: `thesis_os`) |
| `POSTGRES_HOST` | Yes | Database host (default: `localhost`) |
| `POSTGRES_PORT` | Yes | Database port (default: `5432`) |
| `ANTHROPIC_API_KEY` | For `/thesis`, `/stress`, red flags | Claude API key for LLM features |
| `SEC_USER_AGENT` | Yes | Your name + email per [SEC fair-access policy](https://www.sec.gov/os/accessing-edgar-data) |
| `FMP_API_KEY` | No | Financial Modeling Prep key for consensus estimates |

### 3. Start Postgres

```bash
docker compose up -d
```

### 4. Run database migrations

```bash
uv run alembic upgrade head
```

### 5. Start the app

Two terminals:

```bash
# Terminal 1 — Backend (port 8000)
uv run uvicorn app.main:app --port 8000

# Terminal 2 — Frontend (port 5173)
cd frontend && npx vite --port 5173
```

Open **http://localhost:5173** in your browser.

## Usage

### Decision Brief

Enter a ticker on the Brief page to generate a full decision brief. The brief includes:

- **EV Build** — Market cap, debt, cash, enterprise value with source citations
- **Variant Perception** — Reverse DCF implied growth vs consensus vs company guidance
- **Revenue Segments** — Parsed from XBRL filings with YoY growth
- **Sector KPIs** — Quarterly trends, YoY/QoQ deltas, grouped by family (leading/lagging/efficiency/quality)
- **Quality Scores** — Earnings quality, accruals ratio, capital efficiency
- **Institutional Holders** — 13F filers with fund-type classification
- **Insider Activity** — Aggregated Form 4 transactions with 10b5-1 detection
- **Red Flags** — LLM-detected issues with specific numbers cited from filings

Test with curl:
```bash
curl http://localhost:8000/brief/GOOG | python -m json.tool
```

### Thesis Compiler

On the Thesis page, use the `/thesis` command to decompose a plain-English thesis into structured claims, kill criteria, and a catalyst calendar.

```
/thesis AAPL long Services revenue will grow 20% driven by App Store and iCloud adoption
```

Accepted formats:
```
/thesis AAPL long <thesis text>
/thesis AAPL long — <thesis text>
/thesis long AAPL <thesis text>
```

The compiled thesis appears as structured cards on the right panel showing:
- **Thesis Card** — Direction, variant perception, mechanism, disconfirming evidence
- **Claims** — Each claim linked to a KPI with current value and deltas
- **Kill Criteria** — Tripwires with status lights and distance-to-threshold
- **Catalyst Calendar** — Upcoming events sorted by date

### Stress Test

Challenge a thesis or investment memo with adversarial analysis:

```
/stress AAPL — Services revenue will grow 20% because of App Store pricing power
```

Returns circular reasoning checks, already-priced-in analysis, falsification tests, and PM questions.

### Other Commands

| Command | Description |
|---------|-------------|
| `/filing TICKER <query>` | Search filing text for specific language |
| `/evidence TICKER <claim_id>` | Find supporting + disconfirming evidence for a claim |
| `/brief TICKER` | Generate a brief (same as the Brief page) |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/brief/{ticker}` | Generate a Decision Brief |
| `POST` | `/command` | Dispatch a slash command |
| `POST` | `/chat` | Alias for `/command` |
| `POST` | `/thesis/{ticker}` | Compile + persist a thesis |
| `GET` | `/thesis/{id}` | Fetch a saved thesis |
| `GET` | `/theses` | List theses (filter by ticker, status) |
| `PATCH` | `/thesis/{id}/lock` | Lock thesis (draft -> monitoring) |
| `PATCH` | `/thesis/{id}/close` | Close thesis with reason |
| `POST` | `/stress/{ticker}` | Stress test a thesis |
| `GET` | `/export/brief/{ticker}` | Export brief as markdown or PDF |
| `GET` | `/export/thesis/{id}` | Export thesis as markdown |
| `GET` | `/feed/{ticker}` | Change events since a date |
| `GET` | `/health` | Health check |

## Data Sources

- **SEC EDGAR** — XBRL company facts, filing full text, Form 4 insider transactions, 13F holdings, segment revenue from XBRL instance XML
- **Yahoo Finance** — Real-time quotes (price, market cap)
- **US Treasury** — Risk-free rate for WACC calculation
- **FMP** (optional) — Analyst consensus estimates

## Project Structure

```
thesis-os/
  app/
    main.py          # FastAPI routes
    brief.py         # Brief orchestrator + Pydantic response models
    quant.py         # EV build, reverse DCF, sector KPIs, quality scores
    flow.py          # 13F holder map, insider transactions
    qualitative.py   # LLM red flag detection
    thesis.py        # Thesis compiler, command router, stress test
    data.py          # All external data fetching (SEC, Yahoo, Treasury)
    templates.py     # Sector templates (SaaS, semis, banks, E&P, general)
    prompts.py       # LLM prompt constants
    coverage.py      # Driver coverage scoring
    extraction.py    # KPI extraction from filing text
    db.py            # SQLAlchemy models
    crud.py          # Database operations
    export.py        # Markdown + PDF rendering
    changes.py       # Change detection (filings, insider txns, KPI thresholds)
    config.py        # Settings from .env
  frontend/
    src/
      pages/
        BriefPage.tsx    # Decision brief UI
        ThesisPage.tsx   # Chat + thesis cards
        FeedPage.tsx     # Change event feed
      lib/
        api.ts           # API client
        types.ts         # TypeScript types mirroring backend models
        format.ts        # Number formatting utilities
      components/        # Shared UI components
  migrations/            # Alembic migrations
  docker-compose.yml     # Postgres
  pyproject.toml         # Python project config
```
