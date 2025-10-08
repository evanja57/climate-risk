#!/usr/bin/env python3
import os, json, requests, time, asyncio, threading
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any, Iterable, Callable
from urllib.parse import urlparse
from contextlib import contextmanager
from queue import Empty, Queue

from dotenv import load_dotenv

load_dotenv()

from openai import OpenAI
from src.utils import (save_json, slugify, ensure_run_dir, extract_json_from_text, read_prompt, tavily_search_urls, split_identity_transition_queries)
from src.chains import (
    make_queries_chain,
    make_report_chain,
    make_scenario_chain,
)
from src.pdf_utils import (parse_saved_json, parse_saved_firecrawl, pymupdf_pdf_attempt, is_pdf)
from src.fakercrawl import FakerCrawl, FakercrawlFetchError
from src.evidence_md import build_markdown_evidence
from src.markdown_parallel import fetch_markdown_or_none, fetch_many_markdown
from src.tavily_parallel import tavily_search_urls_parallel

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import uvicorn


# --- env & clients ---
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
OPENAI = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

FETCH_TIMEOUT_MS = int(os.getenv("FETCH_TIMEOUT_MS", "20000"))

BACKEND_DIR = Path(__file__).resolve().parent

ALWAYS_ALLOWED_HOST_SUFFIXES = ("sec.gov","annualreports.com","responsibilityreports.com","investor.gov")

BUZZ_STAGES: Dict[str, Dict[str, str]] = {
    "scope": {"headline": "Framing the assessment scope"},
    "aggregate_sources": {
        "headline": "Aggregating relevant sources",
        "note": "Scanning the public web…",
    },
    "rank_filter": {
        "headline": "Ranking and filtering evidence",
        "note": "Sifting signal from noise…",
    },
    "convert_docs": {"headline": "Converting documents for analysis"},
    "synthesize": {
        "headline": "Synthesizing insights",
        "note": "Weaving findings into a coherent brief…",
    },
    "model_risk": {
        "headline": "Modeling transition risk",
        "note": "Stress-testing scenarios and summarizing",
    },
    "finalize": {
        "headline": "Finalizing deliverables",
        "note": "Packaging results for review…",
    },
}


class BuzzObserver:
    """Lightweight observer that relays structured progress events."""

    def __init__(self, emit: Callable[[Dict[str, Any]], None], *, ticker_interval_s: float = 1.0) -> None:
        self._emit = emit
        self._ticker_interval = max(0.1, ticker_interval_s)
        self._last_ticker = 0.0

    def stage_start(self, stage_id: str) -> None:
        payload = {"type": "stage", "id": stage_id, "state": "start"}
        meta = BUZZ_STAGES.get(stage_id, {})
        for key in ("headline", "note"):
            value = meta.get(key)
            if value:
                payload[key] = value
        self._emit(payload)

    def stage_end(self, stage_id: str, *, duration_ms: Optional[int] = None) -> None:
        payload: Dict[str, Any] = {"type": "stage", "id": stage_id, "state": "end"}
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        self._emit(payload)

    def progress(self, stage_id: str, done: int, total: int) -> None:
        self._emit({"type": "progress", "id": stage_id, "done": done, "total": total})

    def metric(self, stage_id: str, key: str, value: Any) -> None:
        self._emit({"type": "metric", "id": stage_id, "key": key, "value": value})

    def artifact(self, stage_id: str, name: str, url: str) -> None:
        self._emit({"type": "artifact", "id": stage_id, "name": name, "url": url})

    def ticker(self, message: str) -> None:
        now = time.monotonic()
        if now - self._last_ticker < self._ticker_interval:
            return
        self._last_ticker = now
        self._emit({"type": "ticker", "message": message})

    def error(self, message: str) -> None:
        self._emit({"type": "error", "message": str(message)})

    def done(self) -> None:
        self._emit({"type": "done"})


@contextmanager
def _stage(observer: Optional[BuzzObserver], stage_id: str):
    """Context manager to auto-emit stage start/end events."""
    started = time.monotonic()
    if observer:
        observer.stage_start(stage_id)
    try:
        yield
    finally:
        if observer:
            duration_ms = int((time.monotonic() - started) * 1000)
            observer.stage_end(stage_id, duration_ms=duration_ms)


def _artifact_url(path: Path) -> str:
    try:
        return str(path.relative_to(BACKEND_DIR))
    except ValueError:
        return str(path)


def _sse_format(event: Dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

def _score(entry: Dict[str, Any]) -> float:
    """Coerce score to float; missing/invalid -> 0.0."""
    try:
        return float(entry.get("score", 0.0))
    except (TypeError, ValueError):
        return 0.0

def top_pdfs_by_bucket(
    results: Dict[str, List[Dict[str, Any]]],
    buckets: Iterable[str] = ("identity", "transition"),
    k: int = 3,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Return top-k PDFs (by descending score) for each requested bucket.
    Keeps original dicts; stable on ties by original order.
    """
    out: Dict[str, List[Dict[str, Any]]] = {}
    for b in buckets:
        entries = results.get(b, []) or []
        # Keep original index to stabilize tie-breaking
        indexed: List[Tuple[int, Dict[str, Any]]] = [(i, e) for i, e in enumerate(entries) if is_pdf(e)]
        # Sort by (-score, original_index)
        indexed.sort(key=lambda ie: (-_score(ie[1]), ie[0]))
        out[b] = [e for _, e in indexed[:k]]
    return out


def top_web_by_bucket(
    results: Dict[str, List[Dict[str, Any]]],
    buckets: Iterable[str] = ("identity", "transition"),
    k: int = 3,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Return top-k non-PDF web results (by descending score) for each bucket.
    """
    out: Dict[str, List[Dict[str, Any]]] = {}
    for b in buckets:
        entries = results.get(b, []) or []
        indexed: List[Tuple[int, Dict[str, Any]]] = [
            (i, e) for i, e in enumerate(entries) if not is_pdf(e)
        ]
        indexed.sort(key=lambda ie: (-_score(ie[1]), ie[0]))
        out[b] = [e for _, e in indexed[:k]]
    return out
    
    
def _format_search_results_md(results: Dict[str, List[Dict[str, Any]]]) -> str:
    lines = ["## Search Results (appendix)\n"]
    for bucket in ("identity", "transition"):
        rows = results.get(bucket, []) or []
        rows = sorted(rows, key=lambda r: -_score(r))
        if not rows:
            continue
        lines.append(f"### {bucket.title()}")
        for r in rows:
            u = r.get("url", "")
            sc = r.get("score", "")
            ct = r.get("content_type", "")
            title = (r.get("title") or "").strip() or "(no title)"
            snip = (r.get("snippet") or "").strip()
            tag = "PDF" if str(ct).lower() == "pdf" or u.lower().endswith(".pdf") else "web"
            lines.append(f"- **{title}** [{tag}] (score: {sc}) — [{u}]({u})")
            if snip:
                lines.append(f"  - _{snip}_")
        lines.append("")  # blank line between buckets
    return "\n".join(lines).strip()
    
    
# --- query generation using generate_queries.txt ---
def generate_queries(company_name: str, run_dir:Path, max_results_per_query: int = 2) -> Dict[str, List[Dict[str, Any]]]:
    """Generates queries, then runs Tavily searches in parallel. Returns bucketed dict."""
    print("\n=== Transition Climate Risk Assessment ===")
    print(f"Company: {company_name}")
    print(f"Max results per query: {max_results_per_query}")

    # run LLM prompt to get the queries
    queries_chain = make_queries_chain()
    print("\nGenerating transition-focused queries...")
    queries: List[str] = queries_chain(company_name)
    
    print("Writing queries to queries.json\n")

    (run_dir / "queries.json").write_text(
        json.dumps(queries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    
    out_json = run_dir / "search_results.json"

    # split to identity/transition 
    identity_queries, transition_queries = split_identity_transition_queries(queries)

    # parallel Tavily across each bucket
    print(f"[parallel] Searching identity queries ({len(identity_queries)})…")
    id_hits = tavily_search_urls_parallel(
        identity_queries,
        per_q=min(max_results_per_query, 3),
        search_depth=os.getenv("TAVILY_DEPTH", "basic"),
        max_workers=int(os.getenv("TAVILY_MAX_WORKERS", "12")),
        qps=int(os.getenv("TAVILY_QPS", "8")),
    )
    print(f"  got {len(id_hits)} hits")

    print(f"[parallel] Searching transition queries ({len(transition_queries)})…")
    tr_hits = tavily_search_urls_parallel(
        transition_queries,
        per_q=max_results_per_query,
        search_depth=os.getenv("TAVILY_DEPTH", "basic"),
        max_workers=int(os.getenv("TAVILY_MAX_WORKERS", "12")),
        qps=int(os.getenv("TAVILY_QPS", "8")),
    )
    print(f"  got {len(tr_hits)} hits")

    # persist in expected shape
    buckets = {
        "identity": [h.to_dict() for h in id_hits],
        "transition": [h.to_dict() for h in tr_hits],
    }
    save_json(run_dir, "search_results.json", buckets)
    print(f"search_results.json written with {len(buckets['identity'])} identity and {len(buckets['transition'])} transition hits")

    return buckets


# --- Generate the decision-ready JSON report using esg_report prompt ---
def generate_report(company: str, evidence_md: str, prompt_path="prompts/esg_report.txt") -> Tuple[dict, str]:
    tmpl = read_prompt(prompt_path)
    
    rendered = tmpl.replace("[COMPANY_NAME]", company).replace("[EVIDENCE]", evidence_md or "Information not provided.")
    
    resp = OPENAI.responses.create(
        model=OPENAI_MODEL,
        input=rendered,
        temperature=1,
    )
    
    content = getattr(resp, "output_text", None)
    if not content:
        content = ""
        output = getattr(resp, "output", None) or getattr(resp, "outputs", None) or []
        for item in output:
            parts = item.get("content") if isinstance(item, dict) else getattr(item, "content", [])
            for p in parts or []:
                text = p.get("text") if isinstance(p, dict) else getattr(p, "text", "")
                if text:
                    content += text
    
    data = extract_json_from_text(content)
    
    if not isinstance(data, dict):
        raise ValueError("Report model did not return the expected JSON object.")
    
    return data, content


def run_assessment(
    company: str,
    *,
    per_q: int = 2,
    pdf_cap: int = 10,
    observer: Optional[BuzzObserver] = None,
) -> tuple[Path, dict]:
    """
    Runs the full pipeline (queries -> search -> scrape -> evidence -> report),
    writes artifacts into a timestamped run_dir, and returns (run_dir, report_json).
    """
    from src.utils import ensure_run_dir, slugify

    with _stage(observer, "scope"):
        run_dir = ensure_run_dir(BACKEND_DIR / "data", slugify(company))
        if observer:
            observer.ticker(f"Scoping transition risk run for {company}")

    with _stage(observer, "aggregate_sources"):
        print("Generating queries")
        search_results = generate_queries(company, run_dir, max_results_per_query=per_q)
        if observer:
            total_sources = sum(len(v or []) for v in search_results.values())
            observer.metric("aggregate_sources", "sources_count", total_sources)
            observer.artifact("aggregate_sources", "queries.json", _artifact_url(run_dir / "queries.json"))
            observer.artifact("aggregate_sources", "search_results.json", _artifact_url(run_dir / "search_results.json"))

    with _stage(observer, "rank_filter"):
        top_pdfs = top_pdfs_by_bucket(search_results, k=pdf_cap)
        pdf_urls = [item["url"] for _, items in top_pdfs.items() for item in items]
        top_webs = top_web_by_bucket(search_results, k=7)
        web_urls = [item["url"] for _, items in top_webs.items() for item in items]
        if observer:
            observer.metric("rank_filter", "pdf_candidates", len(pdf_urls))
            observer.metric("rank_filter", "web_candidates", len(web_urls))

    all_urls = pdf_urls + web_urls

    with _stage(observer, "convert_docs"):
        print(f"[parallel] Converting {len(all_urls)} URLs to markdown…")

        def _progress(done: int, total: int) -> None:
            if observer:
                observer.progress("convert_docs", done, total)

        url_to_md = fetch_many_markdown(
            all_urls,
            max_workers=int(os.getenv("FETCH_MARKDOWN_WORKERS", "6")),
            timeout_ms=FETCH_TIMEOUT_MS,
            politeness_delay_s=float(os.getenv("FETCH_POLITENESS_SECONDS", "0.00")),
            progress_every=10,
            progress_cb=_progress,
        )
        print(f"Successfully got {len(url_to_md)} url's converted to markdown")
        if observer:
            observer.metric("convert_docs", "converted", len(url_to_md))

    global_evidence_registry: Dict[str, Dict[str, Any]] = {}
    evidence_sections: List[str] = []

    with _stage(observer, "synthesize"):
        for url, md in url_to_md.items():
            parsed = urlparse(url)
            base = (parsed.netloc + parsed.path).replace("/", "_")
            md_path = run_dir / f"{slugify(base)}.md"
            md_path.write_text(md, encoding="utf-8")
            print(f"Building evidence sections from markdown: {url}")
            evidence = build_markdown_evidence(
                md_text=md,
                source_url=url,
                top_k=3,                    # down from implicit 6
                max_chars_per_excerpt=650,  # down from 1200
                per_field_top_k={
                    "transition_risks": 5,       # a bit richer
                    "targets_emissions": 3,
                    "strategy_capex_alignment": 3,
                    "product_portfolio_shift": 3,
                    "capital_alignment": 2,
                    "policy_envelopes": 2,
                    "policy_engagement": 2,
                    "climate_governance": 2,
                    "company_identity": 2,
                    "sector_classification": 2,
                    "decarbonisation_programmes": 3,
                    "technology_shift_markets": 2,
                    "ip_moat": 1,
                    "just_transition": 2,
                },
                global_registry=global_evidence_registry,
            )
            evidence_sections.append(evidence)
        search_results_md = _format_search_results_md(search_results)
        (run_dir / "search_results_appendix.md").write_text(search_results_md, encoding="utf-8")
        if observer:
            observer.artifact("synthesize", "search_results_appendix.md", _artifact_url(run_dir / "search_results_appendix.md"))

    evidence_md = ("\n\n---\n\n").join(p for p in evidence_sections if p.strip())
    (run_dir / "evidence.md").write_text(evidence_md, encoding="utf-8")
    if observer:
        observer.artifact("synthesize", "evidence.md", _artifact_url(run_dir / "evidence.md"))

    with _stage(observer, "model_risk"):
        print("Generating final JSON report")
        report_json, raw = generate_report(company, evidence_md)
        (run_dir / "report.json").write_text(json.dumps(report_json, indent=2), encoding="utf-8")
        (run_dir / "report_raw.txt").write_text(raw, encoding="utf-8")
        if observer:
            observer.artifact("model_risk", "report.json", _artifact_url(run_dir / "report.json"))
            observer.artifact("model_risk", "report_raw.txt", _artifact_url(run_dir / "report_raw.txt"))

    with _stage(observer, "finalize"):
        print(f"\nDone. Outputs in: {run_dir.resolve()}")
        if observer:
            observer.ticker("Finalized deliverables and preserved previous artifacts")

    return run_dir, report_json




# ---------------- Web API (FastAPI) ----------------
api = FastAPI(title="Transition Risk Report API", version="1.0.0")

# Allowlist origins via env for public deployment.
# Set ALLOW_ORIGINS to a comma-separated list (e.g., "https://your.site,https://app.site").
# Defaults to "*" for development.
_ALLOW_ORIGINS_ENV = os.getenv("ALLOW_ORIGINS", "*").strip()
_ALLOW_ORIGINS = ["*"] if _ALLOW_ORIGINS_ENV == "*" else [o.strip() for o in _ALLOW_ORIGINS_ENV.split(",") if o.strip()]

api.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@api.post("/api/report")
def create_report(payload: Dict[str, Any]):
    """
    Body:
      {
        "company": "McDonald's",          # required
        "per_q": 2,                       # optional
        "pdf_cap": 5                      # optional
      }
    Response:
      {
        "company": "...",
        "run_dir": "data/<slug>/<timestamp>/transition",
        "report": {...},                  # JSON per prompts/esg_report.txt
        "artifacts": {
          "report_json": "<path>",
          "report_raw": "<path>",
          "evidence_md": "<path>"
        }
      }
    """
    company = (payload or {}).get("company", "")
    if not company or not isinstance(company, str):
        raise HTTPException(status_code=400, detail="Missing 'company' string in request body.")

    per_q = int((payload or {}).get("per_q", 2))
    pdf_cap = int((payload or {}).get("pdf_cap", 5))

    try:
        run_dir, report_json = run_assessment(company, per_q=per_q, pdf_cap=pdf_cap)
        return {
            "company": company,
            "run_dir": str(run_dir),
            "report": report_json,
            "artifacts": {
                "report_json": str(run_dir / "report.json"),
                "report_raw": str(run_dir / "report_raw.txt"),
                "evidence_md": str(run_dir / "evidence.md"),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {e}")


@api.get("/api/report/stream")
async def stream_report(
    request: Request,
    payload: Optional[str] = None,
    company: Optional[str] = None,
    per_q: int = 2,
    pdf_cap: int = 5,
):
    body: Dict[str, Any] = {}
    if payload:
        try:
            body = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid payload JSON: {exc}")

    company_name = (body.get("company") or company or "").strip()
    if not company_name:
        raise HTTPException(status_code=400, detail="Missing 'company' parameter")

    try:
        per_q_value = int(body.get("per_q", per_q))
        pdf_cap_value = int(body.get("pdf_cap", pdf_cap))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="per_q and pdf_cap must be integers")

    event_queue: Queue[str] = Queue()

    def emit(event: Dict[str, Any]) -> None:
        event_queue.put(_sse_format(event))

    observer = BuzzObserver(emit)
    done_event = threading.Event()

    def worker() -> None:
        try:
            run_assessment(
                company_name,
                per_q=per_q_value,
                pdf_cap=pdf_cap_value,
                observer=observer,
            )
        except Exception as exc:
            observer.error(str(exc))
        finally:
            observer.done()
            done_event.set()

    thread = threading.Thread(target=worker, name="sse-pipeline", daemon=True)
    thread.start()

    heartbeat_comment = ": keep-alive\n\n"

    async def event_generator():
        last_heartbeat = time.monotonic()
        while True:
            if done_event.is_set() and event_queue.empty():
                break
            try:
                item = event_queue.get_nowait()
            except Empty:
                await asyncio.sleep(0.25)
                if await request.is_disconnected():
                    done_event.set()
                    break
                if time.monotonic() - last_heartbeat >= 10:
                    last_heartbeat = time.monotonic()
                    yield heartbeat_comment
                continue
            else:
                last_heartbeat = time.monotonic()
                yield item

        while not event_queue.empty():
            try:
                yield event_queue.get_nowait()
            except Empty:
                break

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


def _latest_run_dir_for_company(company_slug: str) -> Optional[Path]:
    base = Path("data") / company_slug
    if not base.exists():
        return None
    # pick latest timestamped run under .../<slug>/*/transition
    candidates = sorted((p for p in base.glob("*/transition") if p.is_dir()), reverse=True)
    for run in candidates:
        if (run / "report.json").exists():
            return run
    # fall back to newest transition directory even if incomplete (preserves original behavior)
    return candidates[0] if candidates else None

@api.get("/api/runs/{company_slug}/latest/report.json")
def get_latest_report(company_slug: str):
    run_dir = _latest_run_dir_for_company(company_slug)
    if not run_dir:
        raise HTTPException(status_code=404, detail="No runs found for that company slug.")
    p = run_dir / "report.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="report.json not found in latest run.")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read report.json.")

@api.get("/api/runs/{company_slug}/latest/evidence.md")
def get_latest_evidence(company_slug: str):
    run_dir = _latest_run_dir_for_company(company_slug)
    if not run_dir:
        raise HTTPException(status_code=404, detail="No runs found for that company slug.")
    p = run_dir / "evidence.md"
    if not p.exists():
        raise HTTPException(status_code=404, detail="evidence.md not found in latest run.")
    return {"text": p.read_text(encoding="utf-8")}
    

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("company", nargs="?", help="Company name (omit if using --serve)")
    ap.add_argument("--per-q", type=int, default=2, help="Tavily max results per query")
    ap.add_argument("--pdf-cap", type=int, default=5, help="Max PDFs to scrape")
    ap.add_argument("--serve", action="store_true", help="Run FastAPI server instead of CLI")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    args = ap.parse_args()

    if args.serve:
        uvicorn.run(api, host=args.host, port=args.port, log_level="info")
    else:
        if not args.company:
            ap.error("company is required in CLI mode (or pass --serve)")
        # Preserve original CLI behavior
        run_assessment(args.company, per_q=args.per_q, pdf_cap=args.pdf_cap)
