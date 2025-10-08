# src/markdown_parallel.py
from __future__ import annotations

import os, time, math, signal, threading, requests, io, re, random
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from typing import Callable, Dict, Iterable, List, Optional
import pymupdf
from .fakercrawl import FakerCrawl, FakercrawlFetchError
from .pdf_utils import tables_to_markdown


# Tunables (env overrides supported)
_DEFAULT_WORKERS = max(2, int(os.getenv("FETCH_MARKDOWN_WORKERS", "6")))
_DEFAULT_TIMEOUT_MS = max(5_000, int(os.getenv("FETCH_TIMEOUT_MS", "20000")))
_DEFAULT_POLITENESS_S = float(os.getenv("FETCH_POLITENESS_SECONDS", "0.00"))  # e.g., 0.05
_FETCH_PDF_TABLES = os.getenv("FETCH_PDF_TABLES", "1") not in ("0","false","False")
_TABLES_MAX_PAGES = int(os.getenv("TABLES_MAX_PAGES", "5"))



# --- PDF table helpers (lightweight: PyMuPDF only) ---

_COL_GAP = 18.0   # min horizontal gap to consider a new column (points)
_ROW_GAP = 6.5    # max vertical distance to group text runs into one row (points)

def _fetch_pdf_bytes(u: str, timeout: float = 30.0) -> bytes:
    backoff = 0.75
    for attempt in range(5):
        try:
            read_timeout = max(1.0, float(timeout))
            connect_timeout = min(10.0, read_timeout)
            r = requests.get(
                u,
                timeout=(connect_timeout, read_timeout),
                headers={"User-Agent": "Mozilla/5.0"},
            )
            r.raise_for_status()
            return r.content
        except Exception:
            if attempt == 4:
                raise
            time.sleep(backoff * (attempt + 1) + random.random() * 0.25)

def _page_spans(doc, page_i: int):
    page = doc.load_page(page_i)
    blocks = page.get_text("dict")["blocks"]
    spans = []
    for b in blocks:
        for l in b.get("lines", []):
            for s in l.get("spans", []):
                t = s.get("text", "").strip()
                if not t:
                    continue
                x, y = float(s["bbox"][0]), float(s["bbox"][1])
                spans.append({"x": x, "y": y, "text": t})
    return spans

def _cluster_rows(spans):
    spans = sorted(spans, key=lambda s: (s["y"], s["x"]))
    rows, cur, last_y = [], [], None
    for s in spans:
        if last_y is None or abs(s["y"] - last_y) <= _ROW_GAP:
            cur.append(s)
            last_y = s["y"] if last_y is None else (last_y + s["y"]) / 2.0
        else:
            rows.append(sorted(cur, key=lambda z: z["x"]))
            cur, last_y = [s], s["y"]
    if cur:
        rows.append(sorted(cur, key=lambda z: z["x"]))
    return rows

def _split_cols(row_spans):
    if not row_spans:
        return []
    cols, prev_x = [[]], None
    for s in row_spans:
        if prev_x is None or (s["x"] - prev_x) < _COL_GAP:
            cols[-1].append(s["text"])
        else:
            cols.append([s["text"]])
        prev_x = s["x"]
    return [" ".join(c).strip() for c in cols]

def _guess_caption(page_text: str):
    lines = [ln.strip() for ln in page_text.splitlines() if ln.strip()]
    top = "\n".join(lines[:8])
    m = re.search(r"(Table\s+\d+[:.\-\s][^\n]+)", top, re.IGNORECASE)
    return m.group(1) if m else None

def _extract_pdf_tables(url: str, max_pages: int | None = None):
    pdf = _fetch_pdf_bytes(url)    
    with pymupdf.open(stream=io.BytesIO(pdf), filetype="pdf") as doc:
        n = doc.page_count if max_pages is None else min(max_pages, doc.page_count)
        out = []
        for i in range(n):
            page = doc.load_page(i)
            spans = _page_spans(doc, i)
            row_spans = _cluster_rows(spans)
            rows = [_split_cols(r) for r in row_spans]
            rows = [r for r in rows if len(r) >= 2]
            if not rows:
                continue
            caption = _guess_caption(page.get_text("text"))
            out.append({"page": i + 1, "rows": rows, "caption": caption})
        return out

crawler = FakerCrawl()
def fetch_markdown_or_none(url: str, timeout_ms: int | None = None) -> Optional[str]:
    """
    Single-URL helper: identical semantics to your current function but exported
    here so it can be used by the parallel runner.
    Returns markdown string or None on failure.
    """
    t_ms = int(_DEFAULT_TIMEOUT_MS if timeout_ms is None else timeout_ms)
    try:
        return crawler.scrape(url, formats=["markdown"], timeout_ms=t_ms, only_main_content=True)["markdown"]
    except FakercrawlFetchError as e:
        print(f"[skip 403/blocked] {url}: {e}")
    except requests.HTTPError as e:
        print(f"[skip http] {url}: {e}")
    except Exception as e:
        print(f"[skip other] {url}: {e}")
    return None


def fetch_many_markdown(
    urls: Iterable[str],
    *,
    max_workers: int = _DEFAULT_WORKERS,
    timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    politeness_delay_s: float = _DEFAULT_POLITENESS_S,
    progress_every: int = 5,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> Dict[str, str]:
    """
    Parallel URL→markdown with graceful KeyboardInterrupt handling.
    - Returns {url: markdown} only for successful fetches.
    - Respects a small per-task politeness delay (optional).
    """
    urls_list: List[str] = [u for u in (urls or []) if isinstance(u, str) and u.strip()]
    if not urls_list:
        return {}

    out: Dict[str, str] = {}
    stop_flag = threading.Event()

    def _worker(u: str) -> tuple[str, Optional[str]]:
        if stop_flag.is_set():
            return (u, None)
        try:
            md = fetch_markdown_or_none(u, timeout_ms=timeout_ms)
            if not md:
                if politeness_delay_s > 0:
                    time.sleep(politeness_delay_s)
                return (u, None)

            # Detect PDFs robustly: URL suffix OR a quick HEAD check.
            is_pdf = u.lower().endswith(".pdf")
            if not is_pdf:
                try:
                    # lightweight HEAD to avoid re-downloading large PDFs
                    h = requests.head(u, timeout=10, allow_redirects=True,
                                    headers={"User-Agent": "Mozilla/5.0"})
                    ctype = h.headers.get("Content-Type", "")
                    is_pdf = "pdf" in ctype.lower()
                except Exception:
                    pass  # ignore HEAD errors; suffix-only detection will suffice

            if is_pdf:
                try:
                    _tables = _extract_pdf_tables(u, max_pages=5)  # cap pages for speed
                    _tmd = tables_to_markdown(_tables)
                    if _tmd:
                        md += "\n\n## Extracted Tables (auto)\n" + _tmd
                except Exception as te:
                    md += f"\n\n<!-- table-extract-error: {te!r} -->"

            if politeness_delay_s > 0:
                time.sleep(politeness_delay_s)
            return (u, md)
        except Exception as e:
            print(f"[worker err] {u}: {e}")
            return (u, None)

    # Make Ctrl-C responsive by ignoring executor swallowing KeyboardInterrupt
    restore_sigint = False
    original_handler = None
    if threading.current_thread() is threading.main_thread():
        try:
            original_handler = signal.getsignal(signal.SIGINT)
            restore_sigint = True
        except (ValueError, AttributeError):
            # Not all platforms/threads allow signal inspection (e.g. when invoked via FastAPI threadpool)
            restore_sigint = False
    try:
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="mdfetch") as ex:
            futures: List[Future] = [ex.submit(_worker, u) for u in urls_list]
            done_count = 0
            total = len(urls_list)
            next_progress = progress_every

            for fut in as_completed(futures):
                try:
                    u, md = fut.result()
                    if md:
                        out[u] = md
                except KeyboardInterrupt:
                    # Propagate: cancel remaining futures and break
                    stop_flag.set()
                    for f in futures:
                        f.cancel()
                    raise
                except Exception as e:
                    print(f"[future err] {e}")

                done_count += 1

                if progress_cb is not None:
                    try:
                        progress_cb(done_count, total)
                    except Exception:
                        pass

                if progress_every > 0 and done_count >= next_progress:
                    pct = math.floor(100.0 * done_count / max(1, total))
                    print(f"[parallel] {done_count}/{total} ({pct}%) completed")
                    next_progress += progress_every
    finally:
        if restore_sigint and original_handler is not None:
            try:
                signal.signal(signal.SIGINT, original_handler)
            except (ValueError, AttributeError):
                pass

    return out
