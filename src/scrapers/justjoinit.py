import logging
import re
from datetime import datetime
from urllib.parse import urlparse

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from src.models import JobOffer

logger = logging.getLogger(__name__)

JUSTJOINIT_OFFERS_URL = "https://justjoin.it/job-offers/all-locations"


def _parse_iso_datetime(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _normalize_company(lines: list[str], title: str) -> str:
    for line in lines:
        if line != title and "/" not in line and "PLN" not in line and len(line) > 1:
            return line
    return "Unknown company"


def _is_salary_line(line: str) -> bool:
    lowered = line.lower()
    return "pln/" in lowered or "undisclosed salary" in lowered


def _parse_salary_line(line: str) -> tuple[int | None, int | None]:
    if not _is_salary_line(line):
        return None, None

    match = re.search(r"(\d[\d\s]*)\s*-\s*(\d[\d\s]*)\s*PLN", line, flags=re.IGNORECASE)
    if not match:
        return None, None

    min_salary = int(match.group(1).replace(" ", ""))
    max_salary = int(match.group(2).replace(" ", ""))
    return min_salary, max_salary


def _is_meta_line(line: str) -> bool:
    stripped = line.strip()
    lowered = stripped.lower()

    if lowered in {"new", "locations", "1-click apply", "super offer"}:
        return True
    if re.fullmatch(r"\d+d left", lowered):
        return True
    if re.fullmatch(r",\s*\+\d+", stripped):
        return True
    return False


def _extract_core_fields(lines: list[str], offer_url: str) -> tuple[str, str, str | None, str | None, int | None, int | None, list[str], str]:
    cleaned_lines = [line for line in lines if line and line.strip()]
    if not cleaned_lines:
        fallback_title = _extract_slug(offer_url).replace("-", " ").title()
        return fallback_title, "Unknown company", None, None, None, None, [], "unknown"

    cursor = 0
    if cleaned_lines[0].strip().lower() == "super offer" and len(cleaned_lines) > 1:
        cursor = 1

    title = cleaned_lines[cursor]
    cursor += 1

    salary_line: str | None = None
    if cursor < len(cleaned_lines) and _is_salary_line(cleaned_lines[cursor]):
        salary_line = cleaned_lines[cursor]
        cursor += 1

    company = "Unknown company"
    company_index = -1
    for index in range(cursor, len(cleaned_lines)):
        candidate = cleaned_lines[index]
        if _is_meta_line(candidate) or _is_salary_line(candidate):
            continue
        company = candidate
        company_index = index
        break

    city: str | None = None
    search_city_from = company_index + 1 if company_index >= 0 else cursor
    for index in range(search_city_from, len(cleaned_lines)):
        candidate = cleaned_lines[index]
        if _is_meta_line(candidate) or _is_salary_line(candidate):
            continue
        if candidate != company:
            city = candidate
            break

    salary_min, salary_max = _parse_salary_line(salary_line or "")

    workplace_type = "unknown"
    if city and "remote" in city.lower():
        workplace_type = "remote"

    slug_lower = _extract_slug(offer_url).lower()
    if workplace_type == "unknown" and "remote" in slug_lower:
        workplace_type = "remote"

    excluded = {title, company}
    if salary_line:
        excluded.add(salary_line)
    if city:
        excluded.add(city)

    skills: list[str] = []
    for line in cleaned_lines:
        if line in excluded or _is_meta_line(line) or _is_salary_line(line):
            continue
        if len(line) < 2:
            continue
        if line not in skills:
            skills.append(line)

    return title, company, city, salary_line, salary_min, salary_max, skills, workplace_type


def _extract_slug(offer_url: str) -> str:
    path_parts = [part for part in urlparse(offer_url).path.split("/") if part]
    if not path_parts:
        return "unknown"
    return path_parts[-1]


class JustJoinItScraper:
    def __init__(self, driver_timeout: int = 15) -> None:
        self.driver_timeout = driver_timeout

    def fetch_offers(self, limit: int = 20) -> list[JobOffer]:
        logger.info("Starting JustJoinIT scrape (limit=%d, timeout=%ds)", limit, self.driver_timeout)
        try:
            raw_items = _collect_offer_links(timeout=self.driver_timeout, limit=limit)
            logger.info("Found %d raw items", len(raw_items))
        except (TimeoutException, WebDriverException) as exc:
            logger.error("Selenium error during scrape: %s", exc)
            return []

        if not raw_items:
            logger.warning("No offers found on JustJoinIT main page")
            return []

        offers: list[JobOffer] = []
        for index, (offer_url, lines) in enumerate(raw_items, 1):
            if len(offers) >= limit:
                break
            try:
                offer = self._to_job_offer(offer_url, lines)
                offers.append(offer)
            except Exception as exc:
                logger.warning("Failed to parse offer %s: %s", offer_url, exc)
                continue

        logger.info("Successfully parsed %d offers", len(offers))
        return offers

    def _to_job_offer(self, offer_url: str, lines: list[str]) -> JobOffer:
        title, company, city, salary_line, salary_min, salary_max, skills, workplace_type = _extract_core_fields(lines, offer_url)

        employment_type: str | None = None
        if salary_line:
            lowered = salary_line.lower()
            if "/h" in lowered:
                employment_type = "b2b"
            elif "/month" in lowered or "/year" in lowered:
                employment_type = "permanent"

        # Safe extraction of slug
        slug = _extract_slug(offer_url)

        return JobOffer(
            source="justjoinit",
            external_id=slug,
            title=title or "Unknown Title",
            company=company,
            city=city,
            workplace_type=workplace_type,
            employment_type=employment_type,
            salary_min_pln=salary_min,
            salary_max_pln=salary_max,
            currency="PLN",
            skills=skills[:12],  # Take top 12 skills
            offer_url=offer_url,
            published_at=None,
        )


def _collect_offer_links(timeout: int, limit: int) -> list[tuple[str, list[str]]]:
    logger.debug("Initializing headless Chrome...")
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--log-level=3")  # Suppress Chrome logs

    driver = webdriver.Chrome(options=options)
    try:
        logger.debug("Navigating to %s", JUSTJOINIT_OFFERS_URL)
        driver.get(JUSTJOINIT_OFFERS_URL)
        
        try:
            logger.debug("Waiting for job offers to load...")
            WebDriverWait(driver, timeout).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, 'a[href*="/job-offer/"]')) > 0
            )
        except TimeoutException:
            logger.warning("Timeout waiting for offers to appear (check selector or network)")
            # Continue anyway, maybe JS loaded some

        logger.debug("Extracting offer links via JS...")
        # Execute JS to get links and text content in one go
        raw_links = driver.execute_script(
            """
            return Array.from(document.querySelectorAll('a[href*="/job-offer/"]')).map(el => ({
                href: el.href,
                text: el.innerText
            }));
            """
        )

        results: list[tuple[str, list[str]]] = []
        seen: set[str] = set()

        if isinstance(raw_links, list):
            for item in raw_links:
                if len(results) >= limit:
                    break
                    
                if not isinstance(item, dict):
                    continue
                    
                href = str(item.get("href") or "").strip()
                if not href or "/job-offer/" not in href or href in seen:
                    continue

                seen.add(href)
                
                # Split text content into lines for parser
                text_content = str(item.get("text") or "")
                lines = [line.strip() for line in text_content.splitlines() if line.strip()]
                
                results.append((href, lines))
        
        return results
    finally:
        driver.quit()


class JustJoinItScraper:
    source = "justjoinit"

    def fetch_offers(self, limit: int = 20, timeout: int = 15) -> list[JobOffer]:
        return fetch_justjoinit_offers(limit=limit, timeout=timeout)