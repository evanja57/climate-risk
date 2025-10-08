# Transition Risk Scout

Transition Risk Scout automates transition-climate-risk due diligence by coupling a FastAPI research pipeline with a Next.js dashboard. The backend orchestrates LLM query generation, Tavily search, evidence extraction, and report synthesis, forming a retrieval-augmented generation (RAG) loop that keeps model outputs grounded in sourced evidence, while the frontend streams structured progress events to analysts in real time.

## Features
- **End-to-end research pipeline** spanning query generation, web/PDF ingestion, markdown evidence routing, and OpenAI-backed synthesis into an ISSB/TCFD-aligned JSON report.
- **Live progress telemetry** via server-sent events (SSE) that surface stage headlines, document conversion progress, artifacts, and ticker updates in the UI.
- **Evidence-first deliverables** including structured JSON, raw model output, a consolidated evidence dossier, and searchable appendices saved per run for auditability.
- **Recovery-friendly storage** where each company assessment is timestamped under `backend/data/<slug>/<timestamp>/transition`, making the latest outputs easy to reload or diff.

## Retrieval-Augmented Generation Workflow
Transition Risk Scout implements a classic RAG pattern to tether large language model reasoning to vetted evidence:
- **Query ideation** – an LLM fabricates company-specific probes that seed the retrieval step.
- **Document retrieval** – Tavily search fans out across the web and PDFs, ranking identity vs. transition-domain sources.
- **Evidence distillation** – fetched documents are converted to markdown and routed into domain buckets with citations.
- **Grounded synthesis** – the OpenAI report prompt ingests the curated evidence and emits JSON summaries with inline references.

This loop runs end-to-end for each assessment so every recommendation remains traceable back to the origin documents captured in `evidence.md` and the artifact appendices.

## Architecture at a Glance
```text
.
├── backend
│   ├── app.py              # FastAPI entrypoint + pipeline orchestration
│   ├── prompts/            # LLM prompt templates (report, scenarios, queries)
│   └── src/                # Pipeline helpers (search, crawling, evidence, utils)
├── frontend
│   ├── app/                # Next.js app router
│   ├── components/         # UI building blocks (ReportCards, ProgressPanel, etc.)
│   ├── hooks/              # Custom hooks (SSE consumer, toast)
│   └── lib/                # API client, slug helpers
├── todo.md                 # Current roadmap and polish tasks
└── progress_sse_implementation.md  # Design doc for the Buzzline progress feature
```

The pipeline stages mirror the BuzzObserver events exposed to the UI:
1. `scope` – establish output folders and slug.
2. `aggregate_sources` – generate LLM queries and parallel Tavily search.
3. `rank_filter` – score and prioritize URLs (PDF vs. web).
4. `convert_docs` – fetch HTML/PDF to markdown with optional table extraction.
5. `synthesize` – route evidence snippets into transition-specific buckets.
6. `model_risk` – render the final JSON report with inline citations.
7. `finalize` – persist artifacts and emit wrap-up tickers.

## Requirements
- Python 3.11+
- Node.js 18+ (Next.js 14 requirement)
- npm 9+ or pnpm/yarn equivalent
- Tavily API key and OpenAI API key for search + report generation

Install Python dependencies with `pip` (see `backend/requirements.txt`) and JavaScript dependencies via `npm install` in `frontend/`.

## Environment Variables
| Variable | Required | Purpose | Default |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | ✅ | Auth for OpenAI `responses` API used in report generation | – |
| `OPENAI_MODEL` | ❌ | Override the OpenAI model name | `gpt-5-mini` |
| `TAVILY_API_KEY` | ✅ | Enables Tavily web search for evidence gathering | – |
| `FETCH_TIMEOUT_MS` | ❌ | Timeout for markdown fetcher | `45000` |
| `FETCH_MARKDOWN_WORKERS` | ❌ | Concurrency for markdown fetch | `6` |
| `FETCH_POLITENESS_SECONDS` | ❌ | Delay between fetches to reduce bot blocks | `0.00` |
| `TAVILY_DEPTH` | ❌ | Tavily search depth (`basic` or `advanced`) | `basic` |
| `TAVILY_MAX_WORKERS` | ❌ | Parallel Tavily worker cap | `12` |
| `TAVILY_QPS` | ❌ | Queries-per-second limiter for Tavily calls | `8` |
| `PORT` | ❌ | Backend serve port when running `python app.py --serve` | `8000` |
| `NEXT_PUBLIC_API_BASE` | ✅ (frontend) | URL the Next.js client should target for API calls | `http://localhost:8000` |

Store secrets in `backend/.env` and `frontend/.env.local` (both git-ignored).

## Quickstart
1. **Clone the repo**
   ```bash
   git clone <repo-url>
   cd climate-risk
   ```
2. **Backend setup**
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate     # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env          # if you maintain one; otherwise create it
   # set OPENAI_API_KEY and TAVILY_API_KEY in .env
   python app.py --serve --host 0.0.0.0 --port 8000
   ```
   - Alternatively run `uvicorn app:api --reload --host 0.0.0.0 --port 8000` while in the `backend/` directory.

3. **Frontend setup**
   ```bash
   cd ../frontend
   npm install
   echo "NEXT_PUBLIC_API_BASE=http://localhost:8000" > .env.local
   npm run dev
   ```
   - Visit `http://localhost:3000` to open Transition Risk Scout.

## Using the Platform
### From the UI
1. Enter a company name and optional tuning parameters (`per_q`, `pdf_cap`).
2. Click **Generate report** to start the pipeline.
3. Watch progress in the Buzzline panel—stage chips, determinate doc conversion meter, ticker, and artifact list update live.
4. When streaming completes the app fetches the latest report/evidence from the backend and renders:
   - Narrative report cards with citation jump links.
   - Raw JSON view (downloadable as `report.json`).
   - Evidence markdown rendered in a reader-friendly panel.

### Command-line invocation
```bash
cd backend
python app.py "Company Name" --per-q 2 --pdf-cap 5
```
Outputs land in `backend/data/<slug>/<timestamp>/transition` with:
- `queries.json`, `search_results.json`
- Markdown per source + `search_results_appendix.md`
- `evidence.md`
- `report.json` and `report_raw.txt`

## API Reference
### `POST /api/report`
Kick off the pipeline synchronously and return the resulting JSON payload.
```bash
curl -X POST http://localhost:8000/api/report \
  -H "Content-Type: application/json" \
  -d '{"company": "Example Corp", "per_q": 2, "pdf_cap": 5}'
```
Response: `{ company, run_dir, report, artifacts }` with paths to saved files.

### `GET /api/report/stream`
Streams structured SSE events while the pipeline runs.
```
GET /api/report/stream?payload={"company":"Example Corp","per_q":2,"pdf_cap":5}
```
Event types include `stage`, `progress`, `metric`, `ticker`, `artifact`, `error`, and `done`. Heartbeat comments are emitted every 10 seconds to keep connections alive.

### Latest artifact helpers
- `GET /api/runs/{company_slug}/latest/report.json`
- `GET /api/runs/{company_slug}/latest/evidence.md`

The frontend uses these endpoints to recover results if the SSE stream drops.

## Evidence & Citation Model
- Markdown ingestion (`src/markdown_parallel.py`) enriches PDFs with auto-extracted tables when available.
- `src/evidence_md.py` routes snippets into transition-specific buckets (targets, capex alignment, policy engagement, etc.).
- `prompts/esg_report.txt` enforces anti-hallucination rules and structured JSON output with inline `[n]` citations.
- The React client’s `SourceAwareText` component renders citations as clickable superscripts tied to the sources map.

## Development Notes
- Pipeline helpers live under `backend/src/` (search, crawling, utils, chains, evidence extraction).
- Progress streaming is coordinated via `BuzzObserver` in `backend/app.py` and rendered through `ProgressPanel` on the frontend.
- `todo.md` tracks prioritized UX improvements (download buttons, expanded inputs, artifact exposure).
- The `progress_sse_implementation.md` design doc explains the Buzzline contract if you extend telemetry.

## Troubleshooting
- **Missing API keys**: The pipeline will short-circuit if `OPENAI_API_KEY` or `TAVILY_API_KEY` is absent—double-check `.env` files.
- **SSE disconnects**: The frontend automatically retries by querying the latest artifacts; ensure the backend run directory is writable.
- **PDF parsing issues**: Adjust `FETCH_TIMEOUT_MS`, `FETCH_POLITENESS_SECONDS`, or disable table extraction by setting `FETCH_PDF_TABLES=0` if large PDFs cause timeouts.
- **Rate limits**: Tune `TAVILY_QPS` or reduce `per_q` to stay within plan quotas.

## Roadmap
Review `todo.md` for upcoming features such as additional pipeline tunables, improved artifact downloads, and UI polish.

## License
Released under the MIT License (see `LICENSE`).

## Public Release Checklist
- Add license (MIT included).
- Confirm no secrets are committed. Keep keys in `backend/.env` and `frontend/.env.local` (both are git-ignored).
- Use the new `ALLOW_ORIGINS` env in the backend to restrict CORS to your domains in production.
- Ensure `backend/data/` (outputs) is git-ignored (already configured).
- Optionally add a short demo GIF/screencast to this README.

### Example `.env` files
- Backend: copy `backend/.env.example` to `backend/.env` and set `OPENAI_API_KEY`, `TAVILY_API_KEY`, and (in production) `ALLOW_ORIGINS` to a comma-separated list of allowed origins.
- Frontend: copy `frontend/.env.local.example` to `frontend/.env.local` and set `NEXT_PUBLIC_API_BASE` to your backend URL.

## Demo Video Tips
- Show the end-to-end run: entering a company, live progress (SSE), and the final report with citations and evidence.
- Use conservative parameters (e.g., `per_q=1`, `pdf_cap=3`) to keep runtime short.
- Consider pre-generating a run and using the "Load latest" option for a quick view.

## Disclaimer
This project is for research and demonstration purposes only and does not constitute investment advice. Model outputs rely on public sources and may be incomplete or out of date.
