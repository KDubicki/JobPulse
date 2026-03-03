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
    return _challenge_reason(html) is not None


def _challenge_reason(html: str) -> str | None:
    lowered = html.lower()
    if "cloudflare" in lowered:
        return "cloudflare"
    if "challenge-platform" in lowered:
        return "challenge-platform"
    if "cierpliwości" in lowered:
        return "cierpliwosc-page"
    if "just a moment" in lowered:
        return "just-a-moment"
    return None


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

    challenge = _challenge_reason(html)
    if challenge is not None:
        logger.warning("TheProtocol HTML recognized as challenge page (%s)", challenge)
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

    logger.debug("TheProtocol HTML extraction produced %d candidate links", len(candidates))
    return candidates


def _fetch_with_requests(timeout: int, retries: int = 2) -> tuple[str | None, str]:
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
            start = time.perf_counter()
            response = requests.get(THEPROTOCOL_OFFERS_URL, timeout=timeout, headers=headers)
            elapsed = time.perf_counter() - start
            logger.debug(
                "TheProtocol requests attempt=%d status=%s elapsed=%.2fs bytes=%d",
                attempt + 1,
                response.status_code,
                elapsed,
                len(response.text),
            )
            response.raise_for_status()
            html = response.text
            challenge = _challenge_reason(html)
            if challenge is not None:
                logger.warning(
                    "TheProtocol responded with challenge page (%s) on attempt %d",
                    challenge,
                    attempt + 1,
                )
                return None, "requests:challenge"
            return html, "requests"
        except requests.RequestException as exc:
            is_last = attempt >= retries
            if is_last:
                logger.error("TheProtocol request failed after retries: %s", exc)
                return None, "requests:error"
            sleep_seconds = 1 + attempt
            logger.warning("TheProtocol request failed (attempt %d/%d): %s; retry in %ss", attempt + 1, retries + 1, exc, sleep_seconds)
            time.sleep(sleep_seconds)

    return None, "requests:unknown"


def _fetch_with_selenium(timeout: int) -> tuple[str | None, str]:
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
        return None, "selenium:init-error"

    try:
        start = time.perf_counter()
        driver.set_page_load_timeout(timeout)
        driver.get(THEPROTOCOL_OFFERS_URL)
        elapsed = time.perf_counter() - start
        html = driver.page_source
        challenge = _challenge_reason(html)
        if challenge is not None:
            logger.warning("Selenium fallback also received challenge page (%s)", challenge)
            return None, "selenium:challenge"
        logger.debug("Selenium fallback succeeded in %.2fs (bytes=%d)", elapsed, len(html))
        return html, "selenium"
    except Exception as exc:
        logger.error("Selenium fallback failed: %s", exc)
        return None, "selenium:error"
    finally:
        driver.quit()


class TheProtocolScraper:
    """Scraper for theprotocol.it job board."""

    source = "theprotocol"

    def fetch_offers(self, limit: int = 20, timeout: int = 15) -> list[JobOffer]:
        run_start = time.perf_counter()
        logger.info("Starting TheProtocol scrape (limit=%d, timeout=%ds)", limit, timeout)

        html, mode = _fetch_with_requests(timeout=timeout, retries=2)
        if html is None:
            html, mode = _fetch_with_selenium(timeout=timeout)
        if html is None:
            logger.warning("TheProtocol scrape finished with no HTML (mode=%s)", mode)
            return []

        logger.info("TheProtocol HTML acquired via mode=%s", mode)

        raw_candidates = _extract_candidates_from_html(html)
        if not raw_candidates:
            logger.warning("No TheProtocol candidates extracted (possibly blocked or layout changed)")
            return []

        logger.info("TheProtocol candidate pool size: %d", len(raw_candidates))

        offers: list[JobOffer] = []
        map_failures = 0
        for candidate in raw_candidates[:limit]:
            try:
                offers.append(_to_job_offer(candidate))
            except Exception as exc:
                map_failures += 1
                logger.warning("Failed to map TheProtocol offer: %s", exc)
                continue

        duration = time.perf_counter() - run_start
        logger.info(
            "Mapped %d TheProtocol offers (failures=%d, duration=%.2fs)",
            len(offers),
            map_failures,
            duration,
        )
        return offers
