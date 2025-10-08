# evidence_md.py
# Build a FIELD-GROUPED *Markdown* evidence bundle from a fakercrawl-style markdown file.
# - Parses markdown into heading-scoped blocks with stable paths
# - Routes & ranks blocks per transition-climate-risk fields
# - Emits a single Markdown string, ready to paste under your esg_report prompt

import difflib
import hashlib
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

# ---------- 0) Router knobs: tailored for transition climate risk ----------

ROUTE: Dict[str, Dict[str, List[str]]] = {
    # COMPANY block (identity, sector, positioning)
    "company_identity": {
        "sections": [
            "Item 1 — Business", "Business", "Overview", "About", "Corporate Information"
        ],
        "keywords": [
            "headquarters", "address", "incorporated", "jurisdiction", "leadership",
            "CEO", "CFO", "ticker", "Nasdaq", "products", "segments", "customers",
            "desalination", "wastewater", "reverse osmosis", "refrigeration", "PX"
        ],
    },
    "sector_classification": {
        "sections": ["Item 1 — Business", "Business", "Overview", "Sales and Marketing", "Project Channels"],
        "keywords": [
            "NAICS", "sector", "sub-sector", "industry", "value chain", "revenue",
            "end markets", "customers", "applications", "water treatment", "industrial",
            "end user", "OEM", "contractor", "installer", "design consultant",
            "CO2", "supermarket", "cold storage"
        ],
    },
    "transition_positioning": {
        "sections": ["Item 1 — Business", "Sustainability", "Strategy", "Market Trends",
                     "Emerging Technologies", "Sales and Marketing"],
        "keywords": [
            "energy efficiency", "decarbonization", "low-carbon", "transition enabler",
            "electrification", "renewable", "process efficiency",
            "PX", "UHP RO", "CO2 refrigeration", "transcritical", "refrigerant",
            "PX G1300", "retrofit", "rack controller", "ease of operation", "design consultants"
        ],
    },

    # TARGETS / EMISSIONS / PROGRAMMES
    "targets_emissions": {
        "sections": [
            "Sustainability", "ESG", "Environmental", "GHG Emissions",
            "Energy and Emissions", "Targets and Metrics", "Operational Impact & Management",
            "Extracted Tables (auto)"
        ],
        "keywords": [
            "scope 1", "scope 2", "scope 3", "co2e", "tco2e", "emissions intensity",
            "baseline", "target", "near-term", "long-term", "net zero", "SBTi",
            "renewable electricity", "RE100", "energy use", "waste", "water",
            "assurance", "limited assurance", "reasonable assurance",
            "ISAE 3000", "ISO 14064-3", "verification", "assurance provider"
        ],
    },
    "decarbonisation_programmes": {
        "sections": ["Sustainability", "Environmental", "Energy and Emissions", "Operations"],
        "keywords": [
            "programme", "program", "initiative", "capex", "investment", "retrofit",
            "efficiency", "electrification", "heat pumps", "PPAs", "renewables", "process changes",
            "supplier engagement", "value chain", "ZLD", "MLD", "UHP", "RO conversion"
        ],
    },
    "climate_governance": {
        "sections": [
            "Directors, Executive Officers and Corporate Governance",
            "Corporate Governance", "Risk Management", "Board Oversight", "Committee",
            "DEF 14A", "Proxy Statement", "Corporate Governance Guidelines",
            "Compensation Committee Charter", "Audit Committee Charter"
        ],
        "keywords": [
            "board", "committee", "oversight", "audit", "sustainability committee",
            "executive compensation", "incentive", "KPI", "clawback", "ESG oversight",
            "proxy", "pay for performance", "performance metric", "short-term incentive",
            "long-term incentive"
        ],
    },
    "policy_engagement": {
        "sections": ["Risk Factors", "Regulation", "Compliance", "Legal and Regulatory", "Operating Environment"],
        "keywords": [
            "lobby", "lobbying", "trade association", "membership", "policy positions",
            "advocacy", "comment letter", "public policy", "political contributions",
            "PAC", "regulatory posture", "compliance", "reporting", "disclosure"
        ],
    },
    
    "capital_alignment": {
        "sections": [
            "EU Taxonomy", "Taxonomy", "Capex", "Capital Expenditures",
            "Investing Activities", "Use of Proceeds", "Sustainable Finance",
            "Financing", "Outlook", "MD&A", "Extracted Tables (auto)"
        ],
        "keywords": [
            "taxonomy alignment", "eligible", "aligned",
            "capex alignment", "opex alignment", "Type C Capex",
            "sustainable finance framework", "green bond", "use of proceeds",
            "capital plan", "investment plan", "low carbon", "R&D",
            "manufacturing expansion"
        ],
    },

    # RISK ASSESSMENT (Policy/Market/Tech/Finance/Supply-chain/Legal)
    "transition_risks": {
        "sections": [
            "Item 1A — Risk Factors", "Risk Factors", "Legal and Regulatory",
            "Operating Environment", "Environmental Regulation", "Compliance"
        ],
        "keywords": [
            # policy & pricing
            "carbon price", "emissions trading", "ETS", "EU ETS", "CBAM", "carbon tax",
            "allowances", "offsets", "border adjustment",
            # disclosure/standards
            "SEC climate rule", "IFRS S2", "ISSB", "TCFD", "CSRD", "ESRS",
            # supply chain/trade/enforcement
            "permit", "enforcement", "sanction", "import duty", "trade barrier",
            # financing / investor
            "cost of capital", "financing", "ESG investors", "lenders",
            # generic risk verbs
            "regulation", "policy", "compliance", "litigation", "lawsuit", "contingent"
        ],
    },

    # METRICS & CAPITAL ALIGNMENT / PORTFOLIO SHIFT
    "strategy_capex_alignment": {
        "sections": [
            "Item 7 — Management’s Discussion and Analysis",
            "MD&A", "Capital Expenditures", "Outlook", "Financial Strategy", "Sales and Marketing"
        ],
        "keywords": [
            "capex", "capital allocation", "investment", "pipeline", "backlog", "margin",
            "IRR", "payback", "portfolio", "product mix", "unit economics", "NPV", "sensitivity",
            "commercialization", "pilot", "field trial", "OEM"
        ],
    },
    "product_portfolio_shift": {
        "sections": ["Business", "Strategy", "Market Trends", "Product Roadmap",
                     "Emerging Technologies", "Sales and Marketing", "Project Channels"],
        "keywords": [
            "low-carbon", "product", "offering", "PX G1300", "CO2 refrigeration", "UHP RO",
            "reverse osmosis", "technology conversion", "thermal to RO", "desalination", "wastewater",
            "OEM", "aftermarket", "contractor", "installer", "field trial", "pilot",
            "commercialization", "go-to-market"
        ],
    },
    "just_transition": {
        "sections": ["Human Capital Resources", "Workforce", "Supply Chain",
                     "Sustainability", "Compensation and Benefits", "Recruiting, Training and Retention"],
        "keywords": [
            "training", "reskilling", "incentive", "KPI", "ESG", "safety",
            "workforce", "community", "supplier", "labor", "local", "equity", "procurement"
        ],
    },

    # Optional: IP defensibility (you can merge this into technology_shift_markets if preferred)
    "ip_moat": {
        "sections": ["Intellectual Property", "Trademarks", "Competition", "Manufacturing"],
        "keywords": ["trademark", "registered", "patent", "IP", "PX", "PX G1300", "logo"],
    },

    # Technology exposure / moat (engineering + sector tech)
    "technology_shift_markets": {
        "sections": ["Pressure Exchanger Technology", "Manufacturing", "Competition",
                     "Emerging Technologies", "Research and Development"],
        "keywords": [
            # engineering competencies / tech moat
            "CFD", "FEA", "tribology", "turbomachinery", "bearings", "ceramic", "alumina",
            # ERII / water & CO₂ specifics
            "PX", "PX G1300", "UHP RO", "ZLD", "MLD", "reverse osmosis", "rack controller"
        ],
    },

    # OPTIONAL envelopes (useful for scenario envelopes / carbon pricing ranges)
    "policy_envelopes": {
        "sections": ["Risk Factors", "Regulation", "Compliance", "Market Risk"],
        "keywords": ["carbon price", "ETS", "CBAM", "carbon tax", "policy", "jurisdiction",
                     "coverage", "allowance", "price range", "per ton"],
    },
}

# Soft blacklist: drop these unless a field keyword hits (keeps generic boilerplate out)
_STOP_SECTIONS = {
    "table of contents", "forward-looking information", "forward-looking statements",
    "seasonality", "compensation and benefits", "recruiting, training and retention",
    "manufacturing", "facilities", "properties", "intellectual property",
    "project channels", "sales and marketing", "additional information",
    "stock information", "investor faqs", "press releases", "contact information",
    "about this report", "executive summary", "investor presentation",
}

_METRIC_REQUIRED_SECTIONS = {"executive summary", "about this report"}

_STRICT_STOP_SECTIONS = {
    "contact us", "contact information", "investor presentation", "more information",
    "safe harbor", "forward-looking statements",
}

_CONTACT_PHRASES_RE = re.compile(r"contact\s+(us|information)|customer\s+service|call\s+us|email\s+us", re.I)
_PHONE_RE = re.compile(r"(\+?\d{1,3}[\s.-]?)?(\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}")
_ADDRESS_RE = re.compile(r"\b\d{1,4}\s+[A-Za-z0-9\.\-\s]+(Street|St\.|Road|Rd\.|Avenue|Ave\.|Boulevard|Blvd\.|Drive|Dr\.|Lane|Ln\.|Suite)\b", re.I)

_PAGE_COMMENT_RE = re.compile(r"<!--\s*page[:\s]+\d+\s*-->", re.I)
_WHITE_PAPER_LINE_RE = re.compile(r"^\s*White Paper:[^\n]+\|\s*\d+\s*$", re.I | re.M)
_WHITE_PAPER_INLINE_RE = re.compile(r"White Paper:[^\n]+\|\s*\d+", re.I)

# Terms that, if present in a Seasonality block, should allow it to pass (CO₂ context)
_CO2_TERMS = {"co2", "transcritical", "refrigeration", "px g1300", "rack controller"}

# Heavy-weighted keywords that are especially discriminative for transition risk
HEAVY = {"cbam", "eu ets", "scope 3", "emissions trading", "carbon price", "sbti", "sec climate rule"}

# Optional engineering/IP patterns: small nudge so they surface when relevant
ENG_IP_PATTERNS = [
    r"\b(CFD|FEA|tribology|turbomachinery|bearings?)\b",
    r"\b(trademark|registered mark|patent|intellectual property|IP)\b",
]

WEIGHTS = {"section": 3.0, "kw_base": 1.0, "kw_heavy": 2.0, "nums": 0.8, "eng_ip": 0.6}

# ---------- 1) Markdown -> heading-scoped blocks ----------

_HEADING_RE = re.compile(r'^(#{1,6})\s+(.*?)(?:\s+\{#([A-Za-z0-9\-\_]+)\})?\s*$', re.M)


def _sanitize_markdown(md_text: str) -> str:
    """Remove boilerplate banners and collapse whitespace before parsing."""
    cleaned = _PAGE_COMMENT_RE.sub("", md_text or "")
    cleaned = _WHITE_PAPER_LINE_RE.sub("", cleaned)
    cleaned = _WHITE_PAPER_INLINE_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _sanitize_fragment(text: str) -> str:
    cleaned = _PAGE_COMMENT_RE.sub(" ", text or "")
    cleaned = _WHITE_PAPER_INLINE_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _normalize_excerpt(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _origin_key(source_url: Optional[str]) -> str:
    if not source_url:
        return "unknown"
    try:
        parsed = urlparse(source_url)
    except Exception:
        return source_url.lower()
    scheme = (parsed.scheme or "http").lower()
    netloc = (parsed.netloc or "").lower()
    path = parsed.path or "/"
    if not path.startswith("/"):
        path = "/" + path
    path = path.rstrip("/") or "/"
    return f"{scheme}://{netloc}{path}"


def _canonical_id_for_excerpt(norm_excerpt: str, origin_key: str) -> str:
    payload = f"{origin_key}::{norm_excerpt}".encode("utf-8", "ignore")
    digest = hashlib.sha1(payload).hexdigest()
    return f"E{digest[:8]}"


def _is_similar(a: str, b: str, threshold: float = 0.9) -> bool:
    if not a or not b:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= threshold


def _is_contact_block(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    if _CONTACT_PHRASES_RE.search(text):
        return True
    composite_hit = "contact" in lower or "phone" in lower or "tel" in lower or "email" in lower
    if composite_hit and (_PHONE_RE.search(text) or "@" in text or _ADDRESS_RE.search(text)):
        return True
    if _ADDRESS_RE.search(text) and not any(term in lower for term in ("scope", "emissions", "target")):
        return True
    return False


def _latest_year_in_text(text: str) -> Optional[int]:
    years = [int(y) for y in re.findall(r"\b(19\d{2}|20\d{2})\b", text or "")]
    if not years:
        return None
    current_year = datetime.utcnow().year
    filtered = [y for y in years if 1900 <= y <= current_year + 1]
    return max(filtered) if filtered else None

def parse_markdown_sections(md_text: str) -> List[Dict[str, Any]]:
    """
    Split markdown into blocks under headings.
    Each block: {level, title, anchor, path, text}
    """
    headings = [(m.start(), len(m.group(1)), m.group(2).strip(), m.group(3) or None)
                for m in _HEADING_RE.finditer(md_text)]
    if not headings:
        # No headings: treat entire document as one block
        return [{"level": 1, "title": "", "anchor": None, "path": "(root)", "text": md_text.strip()}]

    # map heading spans
    spans: List[Tuple[int, int]] = []
    for i, (pos, *_rest) in enumerate(headings):
        end = headings[i + 1][0] if i + 1 < len(headings) else len(md_text)
        spans.append((pos, end))

    blocks: List[Dict[str, Any]] = []
    stack: List[Tuple[int, str]] = []
    for (start, end), (_, level, title, anchor) in zip(spans, headings):
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        path = " > ".join(t for _, t in stack if t)

        # block text is the content until the next heading
        nextline = md_text.find("\n", start)
        block_text = md_text[nextline + 1:end].strip() if nextline != -1 else ""
        blocks.append({
            "level": level,
            "title": title,
            "anchor": anchor,
            "path": path,
            "text": block_text
        })
    return blocks

# ---------- 2) Scoring & selection ----------

def _contains_numbers(s: str) -> bool:
    return bool(re.search(r'(\b20\d{2}\b)|(\d+\.\d+)|(\d+%|\$[\d,]+)', s))

def _passes_stop_sections(block: Dict[str, Any], target: Dict[str, Any]) -> bool:
    """
    Soft blacklist: drop blocks whose *path* hits a stop section,
    unless (a) target keywords hit, or (b) Seasonality+CO2 override is true.
    """
    path = block.get("path", "") or ""
    path_lower = path.lower()

    if _is_contact_block(block.get("text", "")):
        return False

    if any(sec in path_lower for sec in _STRICT_STOP_SECTIONS):
        return False

    hit_section = next((sec for sec in _STOP_SECTIONS if sec in path_lower), None)
    if hit_section:
        t = (block.get("title", "") + " " + block.get("text", "")).lower()
        kw_hit = any(kw.lower() in t for kw in target["keywords"])
        co2_override = ("seasonality" in path_lower) and any(term in t for term in _CO2_TERMS)
        metrics_override = (hit_section in _METRIC_REQUIRED_SECTIONS) and _contains_numbers(t)
        return kw_hit or co2_override or metrics_override
    return True

def score_block(block: Dict[str, Any], target: Dict[str, Any]) -> float:
    """
    Section match (big), keyword matches (base/heavy), numeric presence (small),
    plus a small nudge for engineering/IP regex hits.
    """
    text = (block["title"] + " " + block["path"] + " " + block["text"]).lower()
    score = 0.0

    # section boost
    for sec in target["sections"]:
        if sec.lower() in block["path"].lower():
            score += WEIGHTS["section"]

    # keyword weights
    for kw in target["keywords"]:
        if kw.lower() in text:
            score += WEIGHTS["kw_heavy"] if kw.lower() in HEAVY else WEIGHTS["kw_base"]

    # numeric boost
    if _contains_numbers(text):
        score += WEIGHTS["nums"]

    # engineering/IP light bump
    if any(re.search(p, text, flags=re.I) for p in ENG_IP_PATTERNS):
        score += WEIGHTS["eng_ip"]

    return score

def _extract_numeric_summary(txt: str) -> str:
    """
    Skim the excerpt for quick anchors: % reductions, years, $ amounts, carbon pricing mentions.
    Provides a terse 'Summary:' line above the excerpt.
    """
    parts = []
    percents = re.findall(r'\b\d{1,3}(?:\.\d+)?%', txt)
    years = re.findall(r'\b20\d{2}\b', txt)
    dollars = re.findall(r'\$\s?\d[\d,]*(?:\.\d+)?', txt)
    carbon = re.findall(r'\b(?:carbon price|per ton|$/t|USD/t|EUR/t)\b', txt, flags=re.I)
    if percents:
        parts.append(f"%: {', '.join(percents[:3])}")
    if years:
        parts.append(f"years: {', '.join(sorted(set(years))[:3])}")
    if dollars:
        parts.append(f"$: {', '.join(dollars[:3])}")
    if carbon:
        parts.append("carbon pricing mentioned")
    return " • ".join(parts)

def _trim(text: str, max_chars: int) -> str:
    t = _sanitize_fragment(text.strip())
    return t if len(t) <= max_chars else t[: max_chars - 12].rstrip() + "\n...[snip]..."

def select_blocks(blocks: List[Dict[str, Any]],
                  field: str,
                  cfg: Dict[str, Any],
                  top_k: int,
                  max_chars: int,
                  max_age_years: Optional[int] = 10) -> List[Dict[str, Any]]:
    """
    Rank blocks for a given field and return top_k concise excerpts.
    De-duplicates roughly by excerpt hash to avoid repetitive content.
    """
    scored: List[Tuple[float, Dict[str, Any], str]] = []
    current_year = datetime.utcnow().year
    cutoff_year = current_year - max_age_years if max_age_years is not None else None
    for b in blocks:
        if not _passes_stop_sections(b, cfg):
            continue
        excerpt = _trim(b["text"], max_chars)
        if not excerpt or _is_contact_block(excerpt):
            continue

        s = score_block(b, cfg)
        if s <= 0:
            continue

        if cutoff_year is not None:
            latest_year = _latest_year_in_text(excerpt)
            if latest_year and latest_year < cutoff_year:
                s *= 0.6
        if s <= 0:
            continue
        scored.append((s, b, excerpt))
    scored.sort(key=lambda x: x[0], reverse=True)

    out: List[Dict[str, Any]] = []
    seen_hashes = set()
    for s, b, excerpt in scored:
        h = hash(excerpt[:400])
        if h in seen_hashes:
            continue
        seen_hashes.add(h)
        out.append({
            "path": b["path"],
            "title": b["title"],
            "anchor": b.get("anchor"),
            "summary": _extract_numeric_summary(excerpt),
            "excerpt": excerpt
        })
        if len(out) >= top_k:
            break
    return out

# ---------- 3) Markdown evidence emitter ----------

def build_markdown_evidence(md_text: str,
                            source_url: str = None,
                            top_k: int = 6,
                            max_chars_per_excerpt: int = 1200,
                            per_field_top_k: Dict[str, int] = None,
                            max_age_years: Optional[int] = 10,
                            global_registry: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
    """
    Returns a Markdown string grouped by field:
    # Evidence
    _Source: <url>_
    ## field
    1) Path — Title  [source]
       _Summary:_ ...
       ```md
       excerpt...
       ```
    """
    md_text = _sanitize_markdown(md_text)
    blocks = parse_markdown_sections(md_text)
    sections_md: List[str] = []

    header = "# Evidence\n"
    if source_url:
        header += f"\n_Source: {source_url}_\n"
    sections_md.append(header.rstrip())

    per_field_k = per_field_top_k or {}
    canonical_by_excerpt: Dict[str, str] = {}
    canonical_info: Dict[str, Dict[str, Any]] = {}
    field_outputs: Dict[str, List[Dict[str, str]]] = {}
    seen_by_page: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    local_emitted_ids: Set[str] = set()
    origin_key = _origin_key(source_url)
    if global_registry is not None:
        origin_registry = global_registry.setdefault(origin_key, {})
    else:
        origin_registry: Dict[str, Dict[str, Any]] = {}

    def _format_title(it: Dict[str, Any]) -> str:
        path = (it.get("path") or it.get("title") or "(root)").strip()
        title = (it.get("title") or "").strip()
        return f"{path} — {title}" if title and title not in path else path

    def _page_lookup_key(it: Dict[str, Any]) -> Tuple[str, str]:
        anchor = it.get("anchor") or ""
        path = it.get("path") or it.get("title") or ""
        page_marker = _normalize_excerpt(f"{anchor}::{path}")
        return (source_url or "", page_marker)

    for field, cfg in ROUTE.items():
        k = per_field_k.get(field, top_k)
        picks = select_blocks(
            blocks,
            field,
            cfg,
            top_k=k,
            max_chars=max_chars_per_excerpt,
            max_age_years=max_age_years,
        )
        if not picks:
            continue

        entries: List[Dict[str, str]] = []
        for item in picks:
            norm_excerpt = _normalize_excerpt(item.get("excerpt", ""))
            if not norm_excerpt:
                continue

            page_key = _page_lookup_key(item)
            if any(_is_similar(norm_excerpt, prior) for prior in seen_by_page[page_key]):
                continue
            seen_by_page[page_key].append(norm_excerpt)

            canonical_id = canonical_by_excerpt.get(norm_excerpt)
            canonical_entry: Optional[Dict[str, Any]] = None

            if canonical_id:
                canonical_entry = canonical_info.get(canonical_id) or origin_registry.get(canonical_id)
            else:
                for existing_map in (canonical_info, origin_registry):
                    for cid, meta in existing_map.items():
                        existing_norm = meta.get("norm_excerpt")
                        if existing_norm and _is_similar(norm_excerpt, existing_norm):
                            canonical_id = cid
                            canonical_entry = meta
                            break
                    if canonical_entry:
                        break
                if not canonical_entry:
                    canonical_id = _canonical_id_for_excerpt(norm_excerpt, origin_key)

            canonical_by_excerpt[norm_excerpt] = canonical_id

            if not canonical_entry:
                canonical_entry = {
                    "item": item,
                    "primary_field": field,
                    "fields": {field},
                    "page_key": page_key,
                    "source_url": source_url,
                    "norm_excerpt": norm_excerpt,
                }
                canonical_info[canonical_id] = canonical_entry
                origin_registry[canonical_id] = canonical_entry
                entry_type = "canonical"
                local_emitted_ids.add(canonical_id)
            else:
                canonical_entry.setdefault("norm_excerpt", norm_excerpt)
                canonical_entry.setdefault("fields", set()).add(field)
                canonical_info[canonical_id] = canonical_entry
                origin_registry[canonical_id] = canonical_entry
                if canonical_id in local_emitted_ids:
                    entry_type = "reference"
                else:
                    entry_type = "canonical"
                    local_emitted_ids.add(canonical_id)

            entries.append({"type": entry_type, "id": canonical_id})

        if entries:
            field_outputs[field] = entries

    if not field_outputs:
        return "\n".join(sections_md)

    for field, entries in field_outputs.items():
        sections_md.append(f"\n## {field}\n")
        for idx, entry in enumerate(entries, 1):
            cid = entry["id"]
            canonical_entry = canonical_info[cid]
            canonical_item = canonical_entry["item"]
            link = ""
            link_source = canonical_entry.get("source_url") or source_url
            if link_source:
                anchor = canonical_item.get("anchor")
                link_target = f"{link_source}#{anchor}" if anchor else link_source
                link = f" [[source]]({link_target})"
            title_display = _format_title(canonical_item)

            if entry["type"] == "canonical":
                summary_line = f"_Summary:_ {canonical_item['summary']}" if canonical_item.get("summary") else ""
                block_lines = [f"{idx}. [{cid}] **{title_display}**{link}"]
                if summary_line:
                    block_lines.append(summary_line)
                block_lines.append("")
                block_lines.append("```md")
                block_lines.append(canonical_item["excerpt"])
                block_lines.append("```")
                sections_md.append("\n".join(block_lines))
            else:
                primary_field = canonical_entry["primary_field"].replace('_', ' ')
                sections_md.append(
                    f"{idx}. [{cid}] ↪ see canonical evidence in `{primary_field}`: **{title_display}**{link}"
                )

    return "\n".join(sections_md)

# ---------- 4) (Optional) Simple CLI for local testing ----------

if __name__ == "__main__":
    import argparse
    from pathlib import Path

    ap = argparse.ArgumentParser(description="Build Markdown evidence from fakercrawl.md")
    ap.add_argument("md_path", help="Path to fakercrawl markdown (e.g., fakercrawl.md)")
    ap.add_argument("--source-url", default=None, help="Canonical source URL (for citations)")
    ap.add_argument("--top-k", type=int, default=4, help="Default excerpts per field")
    ap.add_argument("--max-chars", type=int, default=1200, help="Max characters per excerpt")
    args = ap.parse_args()

    md_text = Path(args.md_path).read_text(encoding="utf-8")
    evidence = build_markdown_evidence(
        md_text=md_text,
        source_url=args.source_url,
        top_k=args.top_k,
        max_chars_per_excerpt=args.max_chars,
        per_field_top_k={"transition_risks": max(5, args.top_k)}  # slightly richer field
    )
    print(evidence)
