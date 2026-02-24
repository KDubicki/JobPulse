from datetime import datetime
import re
from urllib.parse import urlparse

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from src.models import JobOffer


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


def _collect_offer_links(timeout: int) -> list[tuple[str, list[str]]]:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(JUSTJOINIT_OFFERS_URL)
        try:
            WebDriverWait(driver, timeout).until(
                lambda current_driver: len(current_driver.find_elements(By.CSS_SELECTOR, 'a[href*="/job-offer/"]')) > 0
            )
        except TimeoutException:
            pass

        seen: set[str] = set()
        results: list[tuple[str, list[str]]] = []

        raw_links = driver.execute_script(
            """
            return Array.from(document.querySelectorAll('a[href*="/job-offer/"]')).map((element) => ({
                href: element.href || '',
                text: element.innerText || ''
            }));
            """
        )

        if isinstance(raw_links, list):
            for item in raw_links:
                if not isinstance(item, dict):
                    continue

                href = str(item.get("href") or "").strip()
                if not href or "/job-offer/" not in href:
                    continue
                if href in seen:
                    continue

                seen.add(href)
                raw_text = str(item.get("text") or "")
                lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
                results.append((href, lines))

        if results:
            return results

        page_source = driver.page_source
        html_links = re.findall(r'href="(https://justjoin\.it/job-offer/[^"]+|/job-offer/[^"]+)"', page_source)
        escaped_links = re.findall(r'https:\\/\\/justjoin\.it\\/job-offer\\/[^"\\]+', page_source)

        for link in html_links:
            normalized = f"https://justjoin.it{link}" if link.startswith("/") else link
            if normalized in seen:
                continue
            seen.add(normalized)
            results.append((normalized, []))

        for escaped_link in escaped_links:
            normalized = escaped_link.replace("\\/", "/")
            if normalized in seen:
                continue
            seen.add(normalized)
            results.append((normalized, []))

        return results
    finally:
        driver.quit()


def _to_job_offer(offer_url: str, lines: list[str]) -> JobOffer:
    title, company, city, salary_line, salary_min, salary_max, skills, workplace_type = _extract_core_fields(lines, offer_url)

    employment_type: str | None = None
    if salary_line:
        lowered = salary_line.lower()
        if "/h" in lowered:
            employment_type = "b2b"
        elif "/month" in lowered or "/year" in lowered:
            employment_type = "permanent"

    return JobOffer(
        source="justjoinit",
        external_id=_extract_slug(offer_url),
        title=title,
        company=company,
        city=city,
        workplace_type=workplace_type,
        employment_type=employment_type,
        salary_min_pln=salary_min,
        salary_max_pln=salary_max,
        currency="PLN",
        skills=skills[:12],
        offer_url=offer_url,
        published_at=None,
    )


def fetch_justjoinit_offers(limit: int = 20, timeout: int = 15) -> list[JobOffer]:
    try:
        raw_items = _collect_offer_links(timeout=timeout)
    except (TimeoutException, WebDriverException):
        return []

    if not raw_items:
        return []

    offers: list[JobOffer] = []
    for offer_url, lines in raw_items[:limit]:
        try:
            offers.append(_to_job_offer(offer_url, lines))
        except Exception:
            continue
    return offers


class JustJoinItScraper:
    source = "justjoinit"

    def fetch_offers(self, limit: int = 20, timeout: int = 15) -> list[JobOffer]:
        return fetch_justjoinit_offers(limit=limit, timeout=timeout)