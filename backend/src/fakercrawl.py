# fakercrawl.py
# Firecrawl-like wrapper that turns a URL (PDF or HTML) into clean Markdown.
# Deps:
#   - Always: requests, pymupdf
#   - For HTML pages: beautifulsoup4, markdownify
from __future__ import annotations
import re
import html
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Tuple, Optional
from urllib.parse import urljoin, urlparse
import random
import time

import requests
import pymupdf  # use pymupdf, not fitz

# Optional imports for HTML mode (guarded)
try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None  # we'll error lazily if HTML path is used without bs4

try:
    from markdownify import markdownify as md_from_html
except Exception:
    md_from_html = None  # we'll error lazily if HTML path is used without markdownify


class FakercrawlFetchError(RuntimeError):
    pass


class FakerCrawl:
    """Lightweight URL→Markdown 'crawler' with a Firecrawl-like interface.

    Public API:
        scrape(url, formats=["markdown"], only_main_content=False, timeout_ms=20000)
            -> {"markdown": "..."}
    """

    def __init__(self, api_key: Optional[str] = None):
        # Kept for interface parity with Firecrawl; not used.
        self.api_key = api_key

    # ---------------- Public API ----------------
    def scrape(
        self,
        url: str,
        formats: Iterable[str] = ("markdown",),
        only_main_content: bool = False,
        timeout_ms: int = 20_000,
    ) -> Dict[str, str]:
        formats = [f.lower() for f in (formats or ())]
        if not formats or "markdown" not in formats:
            raise ValueError("FakerCrawl currently supports only formats=['markdown'].")

        timeout_sec = max(1.0, timeout_ms / 1000.0)
        content_bytes, content_type = self._fetch(url, timeout=timeout_sec)

        if self._is_pdf(url, content_type, content_bytes):
            md = self._pdf_bytes_to_markdown(content_bytes, source_url=url)
        else:
            md = self._html_bytes_to_markdown(
                content_bytes,
                source_url=url,
                only_main_content=only_main_content,
            )
        return {"markdown": md}

    # ---------------- HTTP fetch & type detection ----------------
    @staticmethod
    def _ua_pool() -> list[str]:
        # Small realistic UA pool to dodge naive bot blocks
        return [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        ]

    @staticmethod
    def _base_headers(user_agent: str, referer: str | None = None) -> dict:
        h = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
        }
        if referer:
            h["Referer"] = referer
        return h

    def _fetch(self, url: str, timeout: float = 20.0) -> tuple[bytes, str]:
        """GET with retries and alternate headers; raises FakercrawlFetchError on failure."""
        parsed = urlparse(url)
        referer = f"{parsed.scheme}://{parsed.netloc}/"
        tries = 3
        backoff = 1.25
        last_exc = None
        timeout_sec = max(1.0, float(timeout))
        connect_timeout = min(10.0, timeout_sec)

        for attempt in range(1, tries + 1):
            ua = random.choice(self._ua_pool())
            headers = self._base_headers(ua, referer=referer)

            try:
                resp = requests.get(
                    url,
                    timeout=(connect_timeout, timeout_sec),
                    headers=headers,
                )
                # Some sites return 403/429 on first try; small jitter helps
                if resp.status_code in (403, 429):
                    # One alternate try with slightly different headers
                    time.sleep(backoff * attempt)
                    alt_headers = self._base_headers(random.choice(self._ua_pool()))
                    alt_headers["Accept"] = "application/pdf,text/html;q=0.9,*/*;q=0.8"
                    alt_headers["DNT"] = "1"
                    resp = requests.get(
                        url,
                        timeout=(connect_timeout, timeout_sec),
                        headers=alt_headers,
                    )

                resp.raise_for_status()
                ct = (resp.headers.get("Content-Type") or "").lower()
                return resp.content, ct
            except requests.HTTPError as e:
                last_exc = e
                # Only retry on transient / anti-bot codes
                if resp is not None and resp.status_code not in (401, 402, 403, 404, 408, 409, 423, 425, 429, 500, 502, 503, 504):
                    # Unusual status; break fast
                    break
            except requests.RequestException as e:
                last_exc = e

            # backoff before next attempt
            time.sleep(backoff * attempt + random.uniform(0, 0.25))

        raise FakercrawlFetchError(f"Fetch failed for {url} ({type(last_exc).__name__}: {last_exc})")

    @staticmethod
    def _is_pdf(url: str, content_type: str, content: bytes) -> bool:
        if "pdf" in (content_type or ""):
            return True
        if url.lower().endswith(".pdf"):
            return True
        return content.startswith(b"%PDF")

    # ---------------- Utilities ----------------
    @staticmethod
    def _round_size(s: float, step: float = 0.5) -> float:
        return round(s / step) * step

    @staticmethod
    def _percentile(sorted_vals: List[float], p: float) -> float:
        if not sorted_vals:
            return 0.0
        if p <= 0:
            return sorted_vals[0]
        if p >= 100:
            return sorted_vals[-1]
        k = (len(sorted_vals) - 1) * (p / 100.0)
        f = int(k)
        c = min(f + 1, len(sorted_vals) - 1)
        if f == c:
            return sorted_vals[f]
        d0 = sorted_vals[f] * (c - k)
        d1 = sorted_vals[c] * (k - f)
        return d0 + d1

    @staticmethod
    def _slug(s: str) -> str:
        s = s.strip().lower()
        s = re.sub(r"[’'`]", "", s)
        s = re.sub(r"[^a-z0-9]+", "-", s)
        return s.strip("-")

    @staticmethod
    def _linkify_text_urls(text: str) -> str:
        def repl(m):
            u = m.group(0)
            return f"[{u}]({u})"
        return re.sub(r"(https?://[^\s)\]]+)", repl, text)

    # ---------------- Common cleaning ----------------
    def _strip_math_noise(self, t: str) -> str:
        MATH_NOISE = [
            r"\$\s*\\mathsf\s*\{[^}]+\}\s*\$",
            r"\\left\(|\\right\)|\\otimes|\\boldsymbol|\\mathfrak|\\mathbb|\\ast",
            r"\(\s*\^\s*[\w\\]+\s*\)",
            r"\{\s*\\[A-Za-z]+\s*[^}]*\}",
        ]
        for pat in MATH_NOISE:
            t = re.sub(pat, "", t)
        return re.sub(r"\s{2,}", " ", t).strip()

    def _clean_text(self, t: str) -> str:
        t = t or ""
        t = t.replace("\u00ad", "")                       # soft hyphen
        t = re.sub(r"-\s*\n\s*", "", t)                   # de-hyphenate across lines
        t = re.sub(r"[ \t]+\n", "\n", t)                  # trim trailing spaces
        t = re.sub(r"[ \t]{2,}", " ", t)                  # collapse spaces
        t = html.unescape(t)
        t = self._strip_math_noise(t)
        t = self._linkify_text_urls(t)
        return t.strip()

    # ---------------- Font weight (PDF) ----------------
    @staticmethod
    def _is_bold_by_name(fontname: str) -> bool:
        name = (fontname or "").lower()
        return any(w in name for w in ("bold", "black", "semibold", "demi", "heavy"))

    @staticmethod
    def _is_bold_by_flags(flags: int | None) -> bool:
        return bool((flags or 0) & 2)  # bit 2 commonly indicates bold

    def _is_bold(self, fontname: str, flags: int | None) -> bool:
        return self._is_bold_by_flags(flags) or self._is_bold_by_name(fontname)

    # ---------------- PDF path ----------------
    def _span_iter(self, page):
        data = page.get_text("dict")
        for block in data.get("blocks", []):
            if block.get("type", 0) != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = (span.get("text") or "").strip()
                    if not text:
                        continue
                    yield {
                        "text": text,
                        "size": float(span.get("size", 0.0)),
                        "font": span.get("font", ""),
                        "flags": int(span.get("flags", 0)),
                        "bbox": tuple(span.get("bbox", (0, 0, 0, 0))),
                        "y": float(span.get("bbox", (0, 0, 0, 0))[1]),
                        "x": float(span.get("bbox", (0, 0, 0, 0))[0]),
                    }

    def _derive_heading_bins(self, doc) -> Tuple[float, float, float, float, float]:
        sizes = []
        for page in doc:
            for sp in self._span_iter(page):
                if len(sp["text"]) >= 3:
                    sizes.append(sp["size"])
        if not sizes:
            body = 11.0
            return body, 13.0, 14.5, 16.0, 20.0
        sizes.sort()
        body = self._percentile(sizes, 50.0)
        h4 = max(body * 1.10, self._percentile(sizes, 70))
        h3 = max(body * 1.20, self._percentile(sizes, 80))
        h2 = max(body * 1.35, self._percentile(sizes, 90))
        h1 = max(body * 1.55, self._percentile(sizes, 97))
        return body, h4, h3, h2, h1

    def _group_line_spans(self, page) -> List[Dict]:
        out: List[Dict] = []
        data = page.get_text("dict")
        for block in data.get("blocks", []):
            if block.get("type", 0) != 0:
                continue
            for line in block.get("lines", []):
                spans = [s for s in line.get("spans", []) if (s.get("text") or "").strip()]
                if not spans:
                    continue
                text = "".join(s["text"] for s in spans)
                avg_size = sum(float(s["size"]) for s in spans) / len(spans)
                fontnames = [s.get("font", "") for s in spans]
                flags = [int(s.get("flags", 0)) for s in spans]
                x = min(s["bbox"][0] for s in spans)
                y = min(s["bbox"][1] for s in spans)
                out.append(
                    {
                        "text": self._clean_text(text),
                        "avg_size": avg_size,
                        "is_boldish": any(self._is_bold(f, fl) for f, fl in zip(fontnames, flags)),
                        "x": float(x),
                        "y": float(y),
                    }
                )
        out.sort(key=lambda d: (round(d["y"], 2), round(d["x"], 2)))
        return out

    @staticmethod
    def _is_heading_candidate(text: str) -> bool:
        if not text:
            return False
        if len(text) > 140:
            return False
        if text.count(".") > 2:
            return False
        if re.fullmatch(r"[0-9.\- ]{1,6}", text):
            return False
        alpha_ratio = sum(c.isalnum() for c in text) / max(1, len(text))
        return alpha_ratio >= 0.55

    def _heading_level_from_bins(self, size: float, bold: bool, body: float,
                                 h4: float, h3: float, h2: float, h1: float) -> int:
        if size >= h1:
            lvl = 1
        elif size >= h2:
            lvl = 2
        elif size >= h3:
            lvl = 3
        elif size >= h4:
            lvl = 4
        else:
            return 0
        if bold and lvl < 3:
            lvl = max(1, lvl - 1)
        return lvl

    def _new_paragraph(self, prev: Optional[Dict], cur: Dict, body_size: float) -> bool:
        if not prev:
            return True
        gap = cur["y"] - prev["y"]
        if gap > body_size * 1.2:
            return True
        if cur["x"] < prev["x"] - 6:
            return True
        if (cur["x"] - prev["x"]) > body_size * 0.9:
            return True
        return False

    @staticmethod
    def _as_list_item(text: str) -> Optional[str]:
        m = re.match(r"^\s*([\-\u2022\u2023\u25E6]|[0-9]+[.)])\s+(.*)$", text)
        if not m:
            return None
        bullet, rest = m.groups()
        if bullet and bullet[0].isdigit():
            return f"1. {rest.strip()}"
        return f"- {rest.strip()}"

    def _looks_like_toc(self, lines: List[Dict]) -> bool:
        sample = lines[:120]
        hits = 0
        for ln in sample:
            t = ln["text"]
            if 8 <= len(t) <= 180 and re.search(r"\.{2,}\s*\d{1,3}$", t):
                hits += 1
        return hits >= 8

    def _pdf_bytes_to_markdown(self, pdf_bytes: bytes, source_url: str) -> str:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")

        body_size, h4, h3, h2, h1 = self._derive_heading_bins(doc)

        header_counter = defaultdict(int)
        footer_counter = defaultdict(int)
        pages_lines: List[Tuple[object, List[Dict]]] = []

        for page in doc:
            lines = self._group_line_spans(page)
            h = page.rect.height
            for ln in lines:
                if ln["y"] > 0.92 * h and ln["avg_size"] <= body_size * 0.95:
                    key = (ln["text"].lower(), self._round_size(ln["avg_size"]))
                    footer_counter[key] += 1
                if ln["y"] < 0.08 * h and ln["avg_size"] <= body_size * 0.95:
                    key = (ln["text"].lower(), self._round_size(ln["avg_size"]))
                    header_counter[key] += 1
            pages_lines.append((page, lines))

        min_rep_freq = max(2, int(0.6 * max(1, len(doc))))

        first_heading = None
        scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        md_lines: List[str] = [
            "---",
            f'title: ""',
            f"source_url: {source_url}",
            f"scraped_at: {scraped_at}",
            "format: pdf",
            "---",
            "",
        ]

        for pg_idx, (page, lines) in enumerate(pages_lines, start=1):
            h = page.rect.height
            md_lines.append(f"<!-- page: {pg_idx} -->")
            prev_line: Optional[Dict] = None
            skip_toc = pg_idx <= 4 and self._looks_like_toc(lines)

            for ln in lines:
                text = ln["text"].strip()
                if not text:
                    continue

                key = (text.lower(), self._round_size(ln["avg_size"]))
                if header_counter.get(key, 0) >= min_rep_freq:
                    continue
                if footer_counter.get(key, 0) >= min_rep_freq:
                    continue
                if skip_toc and re.search(r"\.{2,}\s*\d{1,3}$", text):
                    continue

                lvl = self._heading_level_from_bins(
                    ln["avg_size"], ln["is_boldish"], body_size, h4, h3, h2, h1
                )
                if lvl and self._is_heading_candidate(text):
                    if lvl == 1 and not first_heading:
                        first_heading = text
                        md_lines[1] = f'title: "{first_heading.replace(chr(34), "")}"'
                    anchor = self._slug(text)
                    md_lines.append("#" * lvl + f" {text} " + "{#" + anchor + "}")
                    md_lines.append("")
                    prev_line = None
                    continue

                li = self._as_list_item(text)
                if li:
                    if prev_line is None or not self._as_list_item(prev_line["text"] or ""):
                        md_lines.append("")
                    md_lines.append(li)
                    prev_line = ln
                    continue

                if self._new_paragraph(prev_line, ln, body_size):
                    md_lines.append("")
                md_lines.append(text)
                prev_line = ln

            md_lines.append("")

        out: List[str] = []
        prev_blank = False
        for line in md_lines:
            blank = (line.strip() == "")
            if blank and prev_blank:
                continue
            out.append(line)
            prev_blank = blank

        if out[1] == 'title: ""':
            for line in out:
                if line.startswith("# "):
                    out[1] = f'title: "{line[2:].strip().replace(chr(34), "")}"'
                    break

        return "\n".join(out).strip() + "\n"

    # ---------------- HTML path ----------------
    def _html_bytes_to_markdown(self, html_bytes: bytes, source_url: str, only_main_content: bool) -> str:
        if BeautifulSoup is None or md_from_html is None:
            raise RuntimeError(
                "HTML scraping requires 'beautifulsoup4' and 'markdownify'. "
                "Install them with: pip install beautifulsoup4 markdownify"
            )

        enc_guess = "utf-8"
        try:
            text_html = html_bytes.decode(enc_guess, errors="replace")
        except Exception:
            text_html = html_bytes.decode("utf-8", errors="replace")

        soup = BeautifulSoup(text_html, "lxml") if "lxml" in str(type(BeautifulSoup)) else BeautifulSoup(text_html, "html.parser")

        # Drop obvious non-content
        for tag in soup.find_all(["script", "style", "noscript", "template"]):
            tag.decompose()
        for tag in soup.find_all(True, attrs={"aria-hidden": "true"}):
            tag.decompose()

        # Remove nav/header/footer/aside/complementary
        trash_roles = {"navigation", "banner", "complementary", "contentinfo"}
        for tag in soup.find_all(["nav", "header", "footer", "aside"]):
            tag.decompose()
        for tag in soup.find_all(True):
            role = (tag.get("role") or "").lower()
            if role in trash_roles:
                tag.decompose()

        # Resolve relative links & images to absolute
        for a in soup.find_all("a", href=True):
            a["href"] = urljoin(source_url, a["href"])
        for img in soup.find_all("img", src=True):
            img["src"] = urljoin(source_url, img["src"])

        # Choose main content
        root = soup
        main_candidate = None
        if only_main_content:
            # Prefer semantic containers
            for sel in [
                "main article",
                "article",
                "main",
                "[role=main]",
                "#content",
                ".content",
                "#main-content",
                ".post-content",
                ".article__content",
            ]:
                main_candidate = soup.select_one(sel)
                if main_candidate:
                    break
            if not main_candidate:
                # Fallback: pick the element with the most paragraph text
                candidates = soup.find_all(["article", "section", "div"])
                best, best_score = None, 0
                for el in candidates:
                    # simple density score: text length + 50 * number of <p>
                    score = len(el.get_text(" ", strip=True)) + 50 * len(el.find_all("p"))
                    if score > best_score:
                        best, best_score = el, score
                main_candidate = best or soup
            root = main_candidate

        # Title for YAML
        page_title = ""
        if soup.title and soup.title.string:
            page_title = soup.title.string.strip()
        elif root.find("h1"):
            page_title = root.find("h1").get_text(" ", strip=True)

        # Convert to Markdown
        md_body = md_from_html(
            str(root),
            heading_style="ATX",          # #, ##, ###
            bullets="-",                  # normalize bullets
            strip=["span"],               # ignore generic spans
            code_language=False,          # don't guess languages
        )

        # Clean text artifacts, linkify naked URLs again, and trim
        md_body = self._clean_text(md_body)

        scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        front = [
            "---",
            f'title: "{page_title.replace(chr(34), "")}"' if page_title else 'title: ""',
            f"source_url: {source_url}",
            f"scraped_at: {scraped_at}",
            "format: html",
            "---",
            "",
        ]

        # Add slugged IDs to headings (H1–H4) for stable anchors
        out_lines = []
        for line in md_body.splitlines():
            m = re.match(r"^(#{1,4})\s+(.+?)\s*$", line)
            if m:
                hashes, text = m.groups()
                anchor = self._slug(text)
                out_lines.append(f"{hashes} {text} " + "{#" + anchor + "}")
            else:
                out_lines.append(line)

        md = "\n".join(front + out_lines).strip() + "\n"
        return md


# ---- Optional module-level alias, mirroring Firecrawl ergonomics ----
def scrape(url: str, formats: Iterable[str] = ("markdown",), **kwargs) -> Dict[str, str]:
    """Module-level convenience call: fakercrawl.scrape(url, formats=['markdown'])."""
    return FakerCrawl().scrape(url, formats=formats, **kwargs)


if __name__ == "__main__":
    # Example CLI:
    #   python fakercrawl.py https://example.com/a-page
    #   python fakercrawl.py https://example.com/file.pdf
    import sys
    if len(sys.argv) != 2:
        print("Usage: python fakercrawl.py <url>")
        raise SystemExit(1)
    result = scrape(sys.argv[1], formats=["markdown"], only_main_content=True)
    print(result["markdown"])
