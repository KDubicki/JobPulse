import logging
import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from src.models import JobOffer

logger = logging.getLogger(__name__)

THEPROTOCOL_OFFERS_URL = "https://theprotocol.it/praca"


def _looks_like_challenge(html: str) -> bool:
    lowered = html.lower()
    markers = [
        "cloudflare",
        "cierpliwości",
        "just a moment",
        "challenge-platform",
    ]
    return any(marker in lowered for marker in markers)


def _extract_slug(offer_url: str) -> str:
    path_parts = [part for part in urlparse(offer_url).path.split("/") if part]
    if not path_parts:
        return "unknown"
    return path_parts[-1]


def _parse_salary(text: str) -> tuple[int | None, int | None]:
    if not text:
        return None, None

    match = re.search(r"(\d[\d\s]*)\s*[-–]\s*(\d[\d\s]*)\s*(PLN|zł)", text, flags=re.IGNORECASE)
    if not match:
        return None, None

    min_salary = int(match.group(1).replace(" ", ""))
    max_salary = int(match.group(2).replace(" ", ""))
    return min_salary, max_salary


def _normalize_workplace(text: str) -> str:
    lowered = text.lower()
    if "remote" in lowered or "zdal" in lowered:
        return "remote"
    if "hybrid" in lowered or "hybryd" in lowered:
        return "hybrid"
    if "office" in lowered or "biur" in lowered or "on-site" in lowered:
        return "office"
    return "unknown"


def _parse_employment(text: str) -> str | None:
    lowered = text.lower()
    if "b2b" in lowered:
        return "b2b"
    if "uop" in lowered or "employment contract" in lowered:
        return "uop"
    if "mandate" in lowered or "uz" in lowered:
        return "uz"
    return None


def _to_job_offer(raw_offer: dict) -> JobOffer:
    title = raw_offer.get("title") or "Unknown title"
    company = raw_offer.get("company") or "Unknown company"
    city = raw_offer.get("city")
    offer_url = raw_offer.get("offer_url") or THEPROTOCOL_OFFERS_URL

    salary_min, salary_max = _parse_salary(raw_offer.get("salary_text") or "")
    workplace_type = _normalize_workplace(raw_offer.get("workplace_text") or "")
    employment_type = _parse_employment(raw_offer.get("employment_text") or "")

    return JobOffer(
        source="theprotocol",
        external_id=_extract_slug(offer_url),
        title=title,
        company=company,
        city=city,
        workplace_type=workplace_type,
        employment_type=employment_type,
        salary_min_pln=salary_min,
        salary_max_pln=salary_max,
        currency="PLN",
        skills=raw_offer.get("skills") or [],
        offer_url=offer_url,
        published_at=None,
    )


def _extract_candidates_from_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")

    if _looks_like_challenge(html):
        return []

    candidates: list[dict] = []
    seen: set[str] = set()

    for anchor in soup.select("a[href]"):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        if "/praca/" not in href and "/job/" not in href:
            continue

        offer_url = urljoin(THEPROTOCOL_OFFERS_URL, href)
        if offer_url in seen:
            continue
        seen.add(offer_url)

        text_lines = [line.strip() for line in anchor.get_text("\n").splitlines() if line.strip()]
        if not text_lines:
            continue

        title = text_lines[0]
        company = text_lines[1] if len(text_lines) > 1 else "Unknown company"

        city = None
        salary_text = ""
        workplace_text = ""
        employment_text = ""

        for line in text_lines[2:]:
            if city is None and any(token in line.lower() for token in ["warsz", "krak", "wroc", "gda", "pozna", "łód", "remote", "zdal"]):
                city = line
            if not salary_text and re.search(r"\d[\d\s]*\s*[-–]\s*\d[\d\s]*\s*(PLN|zł)", line, flags=re.IGNORECASE):
                salary_text = line
            if not workplace_text and any(token in line.lower() for token in ["remote", "hybrid", "office", "zdal", "hybryd", "biur"]):
                workplace_text = line
            if not employment_text and any(token in line.lower() for token in ["b2b", "uop", "employment", "mandate"]):
                employment_text = line

        candidates.append(
            {
                "title": title,
                "company": company,
                "city": city,
                "salary_text": salary_text,
                "workplace_text": workplace_text,
                "employment_text": employment_text,
                "skills": [],
                "offer_url": offer_url,
            }
        )

    return candidates


def _fetch_with_requests(timeout: int, retries: int = 2) -> str | None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
    }

    for attempt in range(retries + 1):
        try:
            response = requests.get(THEPROTOCOL_OFFERS_URL, timeout=timeout, headers=headers)
            response.raise_for_status()
            html = response.text
            if _looks_like_challenge(html):
                logger.warning("TheProtocol responded with challenge page on attempt %d", attempt + 1)
                return None
            return html
        except requests.RequestException as exc:
            is_last = attempt >= retries
            if is_last:
                logger.error("TheProtocol request failed after retries: %s", exc)
                return None
            sleep_seconds = 1 + attempt
            logger.warning("TheProtocol request failed (attempt %d/%d): %s; retry in %ss", attempt + 1, retries + 1, exc, sleep_seconds)
            time.sleep(sleep_seconds)

    return None


def _fetch_with_selenium(timeout: int) -> str | None:
    logger.info("Trying Selenium fallback for TheProtocol")
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")

    try:
        driver = webdriver.Chrome(options=options)
    except Exception as exc:
        logger.error("Failed to initialize Selenium for TheProtocol fallback: %s", exc)
        return None

    try:
        driver.set_page_load_timeout(timeout)
        driver.get(THEPROTOCOL_OFFERS_URL)
        html = driver.page_source
        if _looks_like_challenge(html):
            logger.warning("Selenium fallback also received challenge page")
            return None
        return html
    except Exception as exc:
        logger.error("Selenium fallback failed: %s", exc)
        return None
    finally:
        driver.quit()


class TheProtocolScraper:
    """Scraper for theprotocol.it job board."""

    source = "theprotocol"

    def fetch_offers(self, limit: int = 20, timeout: int = 15) -> list[JobOffer]:
        logger.info("Starting TheProtocol scrape (limit=%d, timeout=%ds)", limit, timeout)

        html = _fetch_with_requests(timeout=timeout, retries=2)
        if html is None:
            html = _fetch_with_selenium(timeout=timeout)
        if html is None:
            return []

        raw_candidates = _extract_candidates_from_html(html)
        if not raw_candidates:
            logger.warning("No TheProtocol candidates extracted (possibly blocked or layout changed)")
            return []

        offers: list[JobOffer] = []
        for candidate in raw_candidates[:limit]:
            try:
                offers.append(_to_job_offer(candidate))
            except Exception as exc:
                logger.warning("Failed to map TheProtocol offer: %s", exc)
                continue

        logger.info("Mapped %d TheProtocol offers", len(offers))
        return offers
