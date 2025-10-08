# src/tavily_parallel.py
from __future__ import annotations
import os, time, json, math, threading, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional
from urllib.parse import urlparse

from .utils import SearchResult, ALWAYS_ALLOWED_HOST_SUFFIXES

TAVILY_ENDPOINT = "https://api.tavily.com/search"

def _rate_limiter(qps: int):
    """Simple global QPS limiter (thread-safe)."""
    lock = threading.Lock()
    last = 0.0
    interval = 1.0 / max(qps, 1)

    def wait():
        nonlocal last
        with lock:
            now = time.time()
            wait_s = last + interval - now
            if wait_s > 0:
                time.sleep(wait_s)
            last = time.time()
    return wait

def _fetch_one(query: str, api_key: str, per_q: int, search_depth: str, wait, timeout: float, tries: int) -> List[SearchResult]:
    if not query.strip():
        return []
    payload = {
        "api_key": api_key,
        "query": query.strip(),
        "max_results": max(per_q, 1),
        "search_depth": search_depth,
    }
    backoff = 0.75
    for attempt in range(1, tries + 1):
        try:
            wait()  # respect QPS
            resp = requests.post(TAVILY_ENDPOINT, json=payload, timeout=timeout)
            # Retry 429/5xx
            if resp.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"{resp.status_code} retryable")
            resp.raise_for_status()
            data = resp.json() or {}
            results = data.get("results", []) or []
            out: List[SearchResult] = []
            for r in results[: max(per_q, 1)]:
                out.append(
                    SearchResult(
                        query=query,
                        url=str(r.get("url") or "").strip(),
                        title=str(r.get("title") or "").strip(),
                        snippet=str(r.get("content" if "content" in r else "snippet") or "").strip(),
                        score=float(r.get("score") or 0.0) if r.get("score") is not None else None,
                        content_type=str(r.get("content_type") or "").lower(),
                    )
                )
            return out
        except Exception as e:
            if attempt >= tries:
                print(f"[tavily] fail: {query[:120]}… ({e})")
                return []
            # jittered backoff
            time.sleep(backoff * attempt)
    return []

def tavily_search_urls_parallel(
    queries: List[str],
    per_q: int = 2,
    search_depth: str = "basic",
    *,
    max_workers: int = 12,
    qps: int = 8,
    timeout: float = 20.0,
    tries: int = 3,
) -> List[SearchResult]:
    """Parallel Tavily search across queries. Returns flattened SearchResult list."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        print("Missing TAVILY_API_KEY; structured search unavailable.")
        return []

    wait = _rate_limiter(qps)
    results: List[SearchResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [
            ex.submit(_fetch_one, q, api_key, per_q, search_depth, wait, timeout, tries)
            for q in (queries or [])
            if q and q.strip()
        ]
        for fut in as_completed(futs):
            try:
                results.extend(fut.result() or [])
            except Exception as e:
                # already handled in worker; this is a final guard
                print(f"[tavily] worker exception: {e}")
    return results
