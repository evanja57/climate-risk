import json
import pickle
import re
import requests
import pymupdf
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse


_TABLE_KEY_TERMS = {
    "target", "baseline", "status", "scope", "emission", "metric",
    "intensity", "progress", "aligned", "eligible", "goal", "reduction",
    "capex", "opex", "net zero", "co2", "ghg", "assurance",
}

_STATUS_RE = re.compile(r"\b(on track|complete|completed|achieved|met|not met|ahead|behind|in progress|pending|maintained)\b", re.I)
_NUMERIC_RE = re.compile(r"(\b20\d{2}\b|\b\d{2,}\b|\d+%|\$\s?\d[\d,\.]*|\d+\.\d+)")


def parse_saved_json() -> Dict[str, List[Dict[str, Any]]]:
    path = Path("data/energy-recovery-inc/20250926-160548/transition/search_results.json")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    if not isinstance(data, dict):
        raise ValueError("Top-level JSON must be an object mapping bucket -> list[dict].")

    out: Dict[str, List[Dict[str, Any]]] = {}

    for bucket, entries in data.items():
        if not isinstance(entries, list):
            # Skip non-list buckets
            continue

        seen: set[tuple[str, str]] = set()  # (query, url) for dedupe
        cleaned: List[Dict[str, Any]] = []

        for item in entries:
            if not isinstance(item, dict):
                continue

            # Normalize & dedupe by (query, url)
            q = str(item.get("query", "")).strip()
            url = str(item.get("url", "")).strip().lower()

            key = (q, url)
            if url and key in seen:
                continue
            seen.add(key)

            cleaned.append(item)

        out[bucket] = cleaned

    return out
    
def pymupdf_pdf_attempt():
    url = "https://ir.energyrecovery.com/sec-filings/all-sec-filings/content/0001421517-25-000048/0001421517-25-000048.pdf"
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch PDF: {e}")

    with pymupdf.open(stream=resp.content, filetype="pdf") as doc:
        return "\n".join(page.get_text("text") for page in doc)

def parse_saved_firecrawl():
    path  = Path("/home/evanja/climate-risk/data/energy-recovery-inc/20250929-110011/transition/scraped_markdown.pkl")
    out = pickle.loads(path.read_bytes())
    return out


def _is_informative_row(cells: List[str]) -> bool:
    text = " ".join(cells).strip()
    if not text:
        return False
    lower = text.lower()
    return bool(
        _NUMERIC_RE.search(text)
        or _STATUS_RE.search(lower)
        or any(term in lower for term in _TABLE_KEY_TERMS)
    )


def _format_row_values(headers: List[str], row: List[str]) -> str:
    values: List[str] = []
    for idx, cell in enumerate(row[1:], start=1):
        cell = (cell or "").strip()
        if not cell:
            continue
        header_label = (headers[idx] if idx < len(headers) else "").strip()
        if header_label:
            values.append(f"{header_label}: {cell}")
        else:
            values.append(cell)
    return " | ".join(values)


def _tables_to_markdown(tables: List[Dict[str, Any]], *, max_rows: int = 20, max_cols: int = 8) -> str:
    """Format parsed PDF tables into compact bullet lists with numeric/target rows only."""
    if not tables:
        return ""

    table_blocks: List[str] = []
    for table in tables:
        raw_rows = table.get("rows") or []
        if not raw_rows:
            continue

        rows: List[List[str]] = [
            [str(cell or "").strip() for cell in row[:max_cols]]
            for row in raw_rows
        ]

        if len(rows) > 1:
            headers = rows[0]
            data_rows = rows[1:]
        else:
            headers = []
            data_rows = rows

        filtered_rows = [r for r in data_rows if _is_informative_row(r)]
        if not filtered_rows:
            continue

        filtered_rows = filtered_rows[:max_rows]

        caption = (table.get("caption") or "").strip()
        page = table.get("page")
        block_lines: List[str] = []
        heading_bits = []
        if caption:
            heading_bits.append(f"**{caption}**")
        if page:
            heading_bits.append(f"(page {page})")
        if heading_bits:
            block_lines.append(" ".join(heading_bits))

        for row in filtered_rows:
            label = (row[0] if row else "").strip()
            if not label and headers:
                label = headers[0].strip()
            label = label or "Field"
            value_text = _format_row_values(headers, row)
            if value_text:
                block_lines.append(f"- {label}: {value_text}")
            else:
                block_lines.append(f"- {label}")

        table_blocks.append("\n".join(block_lines))

    return "\n\n".join(tb for tb in table_blocks if tb).strip()


# re-export helper for explicit import
tables_to_markdown = _tables_to_markdown


def is_pdf(entry: Dict[str, Any]) -> bool:
    """Detect PDFs via content_type or URL suffix."""
    ct = str(entry.get("content_type", "")).strip().lower()
    if ct == "pdf":
        return True
    url = str(entry.get("url", "")).strip()
    if not url:
        return False
    path = urlparse(url).path.lower()
    return path.endswith(".pdf")
