"""Job description scraper service.

Fetches job postings from public URLs and extracts the job description text.
Supports LinkedIn, Greenhouse, Lever, Workday, and generic job boards.

LinkedIn Notes
--------------
LinkedIn public job pages embed structured data as JSON-LD (application/ld+json).
We parse that first since it's the most reliable; if blocked we fall back to
meta-tag extraction. LinkedIn increasingly requires login for full pages, so
the scraper returns whatever it can extract and signals partial results.
"""

import json
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

# Realistic browser headers to reduce bot-detection rejections
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_TIMEOUT = 10.0  # seconds


class JobFetchError(Exception):
    """Raised when the job page cannot be fetched or parsed."""


def _extract_json_ld(soup: BeautifulSoup) -> str | None:
    """Extract job description from JSON-LD structured data (most reliable)."""
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            # Handle both single object and list
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") in ("JobPosting", "jobPosting"):
                    desc = item.get("description", "")
                    title = item.get("title", "")
                    company = ""
                    if isinstance(item.get("hiringOrganization"), dict):
                        company = item["hiringOrganization"].get("name", "")
                    parts = []
                    if title:
                        parts.append(f"Job Title: {title}")
                    if company:
                        parts.append(f"Company: {company}")
                    if desc:
                        # Strip HTML tags inside the description
                        clean = BeautifulSoup(desc, "html.parser").get_text(separator="\n")
                        parts.append(clean)
                    if parts:
                        return "\n\n".join(parts)
        except (json.JSONDecodeError, AttributeError):
            continue
    return None


def _extract_meta_description(soup: BeautifulSoup) -> str | None:
    """Fallback: extract from og:description / meta description."""
    tag = soup.find("meta", property="og:description") or soup.find(
        "meta", attrs={"name": "description"}
    )
    if tag and tag.get("content"):
        return tag["content"].strip()
    return None


def _extract_linkedin(soup: BeautifulSoup, html: str) -> str | None:
    """LinkedIn-specific extraction — tries JSON-LD then decorated sections."""
    # 1. Try JSON-LD
    result = _extract_json_ld(soup)
    if result:
        return result

    # 2. LinkedIn embeds job data in a <code> block as JSON
    for code_tag in soup.find_all("code"):
        text = code_tag.get_text()
        if "jobDescription" in text or "description" in text:
            # Extract raw text content — messy but salvageable
            clean = BeautifulSoup(text, "html.parser").get_text(separator="\n")
            if len(clean) > 200:
                return clean[:8000]

    # 3. Last resort: main content divs
    selectors = [
        "div.description__text",
        "div.show-more-less-html__markup",
        "section.description",
        "div[class*='description']",
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            return el.get_text(separator="\n").strip()[:8000]

    return None


def _is_linkedin_url(url: str) -> bool:
    return "linkedin.com" in urlparse(url).netloc


async def fetch_job_description(url: str) -> dict:
    """
    Fetch a job posting URL and extract the job description.

    Returns:
        {
            "success": bool,
            "job_description": str,   # extracted text (may be partial)
            "source": str,            # "json_ld" | "meta" | "html" | "error"
            "warning": str | None,    # set if result may be incomplete
        }
    """
    try:
        async with httpx.AsyncClient(
            headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True
        ) as client:
            resp = await client.get(url)
    except httpx.TimeoutException:
        raise JobFetchError("Request timed out. The job site may be slow or unavailable.") from None
    except httpx.RequestError as exc:
        raise JobFetchError(f"Network error: {exc}") from exc

    if resp.status_code == 999:
        # LinkedIn's bot-detection rejection code
        raise JobFetchError(
            "LinkedIn blocked the request (HTTP 999). "
            "Please paste the job description text manually."
        )
    if resp.status_code in (401, 403):
        raise JobFetchError(
            f"Access denied (HTTP {resp.status_code}). "
            "This job posting requires a login. Please paste the description manually."
        )
    if not resp.is_success:
        raise JobFetchError(f"Failed to fetch page (HTTP {resp.status_code}).")

    soup = BeautifulSoup(resp.text, "html.parser")
    warning = None

    # Remove noise
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    if _is_linkedin_url(url):
        text = _extract_linkedin(soup, resp.text)
        source = "linkedin"
        if not text:
            # LinkedIn likely requires login — return meta desc as partial
            text = _extract_meta_description(soup)
            source = "meta"
            warning = (
                "LinkedIn returned limited content — the full description may require login. "
                "Consider pasting the job description manually for best results."
            )
    else:
        # Generic: JSON-LD → meta → body paragraphs
        text = _extract_json_ld(soup)
        source = "json_ld"
        if not text:
            text = _extract_meta_description(soup)
            source = "meta"
        if not text:
            # Grab the longest text block on the page
            paragraphs = [p.get_text(separator=" ").strip() for p in soup.find_all("p")]
            big = [p for p in paragraphs if len(p) > 100]
            text = "\n\n".join(big[:30]) if big else None
            source = "html"

    if not text or len(text.strip()) < 50:
        raise JobFetchError(
            "Could not extract job description from this URL. " "Please paste the text manually."
        )

    # Normalize whitespace
    text = re.sub(r"\n{3,}", "\n\n", text.strip())

    return {
        "success": True,
        "job_description": text[:10_000],  # cap at our API field limit
        "source": source,
        "warning": warning,
    }
