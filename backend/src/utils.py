# --- utils.py ---
from pathlib import Path
import os, json, time, re, requests
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any
from urllib.parse import urlparse
from dataclasses import dataclass
from dotenv import load_dotenv


load_dotenv()


ALWAYS_ALLOWED_HOST_SUFFIXES = ("sec.gov","annualreports.com","responsibilityreports.com","investor.gov")
IDENTITY_QUERY_COUNT = 4

@dataclass
class SearchResult:
    """Structured Tavily search hit preserved for downstream processing."""

    query: str
    url: str
    title: str
    snippet: str
    score: Optional[float]
    content_type: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "url": self.url,
            "title": self.title,
            "snippet": self.snippet,
            "score": self.score,
            "content_type": self.content_type,
        }


def tavily_search_urls(
    queries: List[str],
    per_q: int = 2,
    search_depth: str = "basic",
    company_terms: Optional[List[str]] = None,
) -> List[SearchResult]:
    """Return Tavily results as structured objects for richer downstream use."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        print("Missing TAVILY_API_KEY; structured search unavailable.")
        return []

    results: List[SearchResult] = []
    normalised_terms = [term.lower() for term in (company_terms or []) if term]

    def _prioritize_hits(items: List[SearchResult], raw_query: str) -> List[SearchResult]:
        if not items:
            return items
        lowered_query = raw_query.lower()
        if 'site:' in lowered_query or not normalised_terms:
            return items
        prioritised: List[SearchResult] = []
        fallback: List[SearchResult] = []
        for item in items:
            host = urlparse(item.url).hostname or ''
            host_clean = host.lower().lstrip('www.')
            if any(term and term in host_clean for term in normalised_terms):
                prioritised.append(item)
            elif host_clean.endswith(ALWAYS_ALLOWED_HOST_SUFFIXES):
                prioritised.append(item)
            else:
                fallback.append(item)
        return prioritised + fallback

    for raw_query in queries or []:
        query = (raw_query or "").strip()
        if not query:
            continue

        payload = {
            "api_key": api_key,
            "query": query,
            "max_results": max(per_q, 1),
            "search_depth": search_depth,
        }

        try:
            response = requests.post(
                "https://api.tavily.com/search",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=40,
            )
        except requests.RequestException as exc:
            print(f"Error searching query '{query[:80]}...': {exc}")
            continue

        if response.status_code != 200:
            try:
                error_body = response.text
            except Exception:
                error_body = ""
            print(f"Tavily API error {response.status_code} for '{query[:80]}...': {error_body[:200]}")
            continue

        try:
            data = response.json()
        except ValueError:
            print(f"Malformed JSON from Tavily for '{query[:80]}...'")
            continue

        effective_query = (data.get("query") or query).strip()
        hits = data.get("results") or []
        processed: List[SearchResult] = []

        for hit in hits:
            if not isinstance(hit, dict):
                continue
            url = (hit.get("url") or "").strip()
            if not url:
                continue
            result = SearchResult(
                query=effective_query,
                url=url,
                title=(hit.get("title") or "").strip(),
                snippet=(hit.get("content") or hit.get("snippet") or "").strip(),
                score=hit.get("score"),
                content_type=(hit.get("content_type") or hit.get("type") or "webpage"),
            )
            processed.append(result)

        ordered_hits = _prioritize_hits(processed, query)
        unique_hits: List[SearchResult] = []
        seen_urls = set()
        for item in ordered_hits:
            if item.url in seen_urls:
                continue
            seen_urls.add(item.url)
            unique_hits.append(item)
            if len(unique_hits) >= per_q:
                break

        results.extend(unique_hits)

    return results

def slugify(value: str) -> str:
    value = (value or "").lower().strip()
    value = re.sub(r"https?://", "", value)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "company"

def ensure_run_dir(base_dir: str, slug: str) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    run_path = Path(base_dir) / slug / timestamp / "transition"
    run_path.mkdir(parents=True, exist_ok=True)
    return run_path

def extract_json_from_text(blob: str):
    blob = (blob or "").strip()
    try:
        return json.loads(blob)
    except Exception:
        pass
    stack, start = [], None
    for i, ch in enumerate(blob):
        if ch in "{[":
            if not stack: start = i
            stack.append(ch)
        elif ch in "}]":
            if stack: stack.pop()
            if not stack and start is not None:
                candidate = blob[start:i+1]
                try:
                    return json.loads(candidate)
                except Exception:
                    pass
    return None

def read_prompt(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")



def split_identity_transition_queries(queries: List[str], identity_count: int = IDENTITY_QUERY_COUNT) -> Tuple[List[str], List[str]]:
    identity = queries[:identity_count]
    transition = queries[identity_count:]
    return identity, transition


def save_json(dirpath: Path, filename: str, data: Any) -> None:
    (dirpath / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")