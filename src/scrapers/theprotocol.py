import logging
import os
import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import json

from src.models import JobOffer

logger = logging.getLogger(__name__)

THEPROTOCOL_OFFERS_URL = "https://theprotocol.it/praca"
THEPROTOCOL_API_URL = (
    "https://apus-api.theprotocol.it/v2/recommendations"
    "?context=listing&source=protocol&offset={offset}&limit={limit}"
)


def _parse_cookie_header(cookie_header: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for chunk in cookie_header.split(";"):
        if "=" not in chunk:
            continue
        name, value = chunk.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name:
            cookies[name] = value
    return cookies


def _build_session() -> requests.Session:
    session = requests.Session()
    user_agent = os.environ.get(
        "JOBPULSE_THEPROTOCOL_USER_AGENT",
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    )
    session.headers.update(
        {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Referer": os.environ.get("JOBPULSE_THEPROTOCOL_REFERER", "https://www.google.com/"),
        }
    )

    cookie_header = os.environ.get("JOBPULSE_THEPROTOCOL_COOKIE", "").strip()
    if cookie_header:
        parsed = _parse_cookie_header(cookie_header)
        session.cookies.update(parsed)
        logger.info("Using custom TheProtocol cookies from JOBPULSE_THEPROTOCOL_COOKIE (%d keys)", len(parsed))

    return session


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


def _safe_get(item: dict, keys: list[str]) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _normalize_offer_url(raw: str | None) -> str | None:
    if not raw:
        return None
    if raw.startswith("http"):
        return raw
    return urljoin("https://theprotocol.it/", raw)


def _extract_candidates_from_api(payload: object) -> list[dict]:
    if payload is None:
        return []

    items: list[dict] = []

    if isinstance(payload, list):
        items = [item for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict):
        # Try common containers
        for key in ["offers", "items", "results", "data", "payload", "elements", "hits", "list"]:
            value = payload.get(key)
            if isinstance(value, list):
                items = [item for item in value if isinstance(item, dict)]
                break
        if not items:
            # Try nested
            for key in ["data", "payload"]:
                value = payload.get(key)
                if isinstance(value, dict):
                    for inner in ["offers", "items", "results", "list"]:
                        inner_value = value.get(inner)
                        if isinstance(inner_value, list):
                            items = [item for item in inner_value if isinstance(item, dict)]
                            break

    candidates: list[dict] = []
    for item in items:
        title = _safe_get(item, ["title", "position", "name"])
        company = _safe_get(item, ["companyName", "company", "employer", "brandName", "organization"])
        city = _safe_get(item, ["city", "location", "cityName"])
        offer_url = _normalize_offer_url(
            _safe_get(item, ["offerUrl", "url", "link", "applyUrl", "slug"]) or ""
        )

        salary_text = _safe_get(item, ["salary", "salaryText", "salaryRange", "salaryPln"]) or ""
        workplace_text = _safe_get(item, ["workplaceType", "workplace", "remote", "mode"]) or ""
        employment_text = _safe_get(item, ["employmentType", "contractType", "contract"]) or ""

        skills = item.get("skills") or item.get("tech") or item.get("stack")
        if isinstance(skills, list):
            skills_list = [str(s).strip() for s in skills if str(s).strip()]
        else:
            skills_list = []

        candidates.append(
            {
                "title": title or "Unknown title",
                "company": company or "Unknown company",
                "city": city,
                "salary_text": salary_text,
                "workplace_text": workplace_text,
                "employment_text": employment_text,
                "skills": skills_list,
                "offer_url": offer_url or THEPROTOCOL_OFFERS_URL,
            }
        )

    logger.debug("TheProtocol API extraction produced %d candidate offers", len(candidates))
    return candidates


def _build_candidate(offer_url: str, text_lines: list[str]) -> dict | None:
    if not text_lines:
        return None

    title = text_lines[0]
    company = text_lines[1] if len(text_lines) > 1 else "Unknown company"

    city = None
    salary_text = ""
    workplace_text = ""
    employment_text = ""

    for line in text_lines[2:]:
        lowered = line.lower()
        if city is None and any(token in lowered for token in ["warsz", "krak", "wroc", "gda", "pozna", "łód", "remote", "zdal"]):
            city = line
        if not salary_text and re.search(r"\d[\d\s]*\s*[-–]\s*\d[\d\s]*\s*(PLN|zł)", line, flags=re.IGNORECASE):
            salary_text = line
        if not workplace_text and any(token in lowered for token in ["remote", "hybrid", "office", "zdal", "hybryd", "biur"]):
            workplace_text = line
        if not employment_text and any(token in lowered for token in ["b2b", "uop", "employment", "mandate"]):
            employment_text = line

    return {
        "title": title,
        "company": company,
        "city": city,
        "salary_text": salary_text,
        "workplace_text": workplace_text,
        "employment_text": employment_text,
        "skills": [],
        "offer_url": offer_url,
    }


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
        candidate = _build_candidate(offer_url, text_lines)
        if candidate:
            candidates.append(candidate)

    logger.debug("TheProtocol HTML extraction produced %d candidate links", len(candidates))
    return candidates


def _fetch_with_requests(timeout: int, retries: int = 2) -> tuple[str | None, str]:
    session = _build_session()

    for attempt in range(retries + 1):
        try:
            start = time.perf_counter()
            response = session.get(THEPROTOCOL_OFFERS_URL, timeout=timeout)
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


def _fetch_api_with_requests(limit: int, timeout: int) -> list[dict]:
    session = _build_session()
    url = THEPROTOCOL_API_URL.format(offset=0, limit=limit)
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        return _extract_candidates_from_api(payload)
    except requests.RequestException as exc:
        logger.warning("TheProtocol API request failed: %s", exc)
        return []
    except ValueError as exc:
        logger.warning("TheProtocol API response is not JSON: %s", exc)
        return []


def _fetch_with_selenium(timeout: int) -> tuple[str | None, str, list[dict] | None]:
    logger.info("Trying Selenium fallback for TheProtocol")
    options = Options()
    headless_env = os.environ.get("JOBPULSE_THEPROTOCOL_HEADLESS", "1").strip().lower()
    interactive_env = os.environ.get("JOBPULSE_THEPROTOCOL_INTERACTIVE", "0").strip().lower()
    interactive = interactive_env in {"1", "true", "yes"}

    # In interactive mode we must show the browser to allow manual challenge solve.
    if interactive:
        headless_env = "0"
    if headless_env not in {"0", "false", "no"}:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")

    user_agent = os.environ.get(
        "JOBPULSE_THEPROTOCOL_USER_AGENT",
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    )
    options.add_argument(f"--user-agent={user_agent}")

    debug_net = os.environ.get("JOBPULSE_THEPROTOCOL_DEBUG_NET", "0").strip().lower() in {"1", "true", "yes"}
    api_discovery = os.environ.get("JOBPULSE_THEPROTOCOL_API_DISCOVERY", "1").strip().lower() in {"1", "true", "yes"}
    if debug_net or api_discovery:
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    try:
        driver = webdriver.Chrome(options=options)
    except Exception as exc:
        logger.error("Failed to initialize Selenium for TheProtocol fallback: %s", exc)
        return None, "selenium:init-error", None

    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            },
        )

        start = time.perf_counter()
        cookie_header = os.environ.get("JOBPULSE_THEPROTOCOL_COOKIE", "").strip()
        if cookie_header:
            driver.get("https://theprotocol.it/")
            for name, value in _parse_cookie_header(cookie_header).items():
                try:
                    driver.add_cookie({"name": name, "value": value, "domain": ".theprotocol.it", "path": "/"})
                except Exception:
                    continue

        driver.set_page_load_timeout(timeout)
        driver.get(THEPROTOCOL_OFFERS_URL)
        elapsed = time.perf_counter() - start
        html = driver.page_source
        challenge = _challenge_reason(html)
        if debug_net:
            _dump_network_requests(driver)

        if challenge is not None:
            logger.warning("Selenium fallback also received challenge page (%s)", challenge)
            if interactive:
                logger.info(
                    "Interactive mode enabled. Solve the challenge in the opened browser, then press Enter here."
                )
                try:
                    input("Press Enter after completing the challenge...")
                except EOFError:
                    time.sleep(10)

                html = driver.page_source
                if debug_net:
                    _dump_network_requests(driver)
                challenge = _challenge_reason(html)
                if challenge is not None:
                    logger.warning("Challenge still present after interactive wait (%s)", challenge)
                    return None, "selenium:challenge", None
            else:
                return None, "selenium:challenge", None

        if interactive:
            logger.info("Tip: you can export cookies for reuse via JOBPULSE_THEPROTOCOL_COOKIE")
            logger.info("Example: cf_clearance=...; __cf_bm=... (copy from your browser devtools)")
        logger.debug("Selenium fallback succeeded in %.2fs (bytes=%d)", elapsed, len(html))

        api_candidates = []
        if api_discovery:
            api_url = _discover_api_url_from_logs(driver)
            if not api_url:
                api_url = _discover_api_url_from_dump_file()
            if api_url:
                logger.info("Discovered API URL for Selenium fetch: %s", api_url)
                api_candidates = _fetch_api_url_with_selenium(driver, api_url)

        if not api_candidates:
            api_candidates = _fetch_api_with_selenium(driver, limit=50)
        if api_candidates:
            logger.info("Extracted %d candidates from API via Selenium", len(api_candidates))
            return html, "selenium:api", api_candidates

        dom_candidates = _extract_candidates_from_dom(driver)
        if dom_candidates:
            logger.info("Extracted %d candidates directly from DOM", len(dom_candidates))
            return html, "selenium:dom", dom_candidates

        return html, "selenium", None
    except Exception as exc:
        logger.error("Selenium fallback failed: %s", exc)
        return None, "selenium:error", None
    finally:
        driver.quit()


def _extract_candidates_from_dom(driver: webdriver.Chrome) -> list[dict]:
    try:
        raw_links = driver.execute_script(
            """
            return Array.from(document.querySelectorAll('a[href]')).map(el => ({
                href: el.href || '',
                text: (el.innerText || '').trim()
            }));
            """
        )
    except Exception as exc:
        logger.debug("DOM extraction failed: %s", exc)
        return []

    if not isinstance(raw_links, list):
        return []

    candidates: list[dict] = []
    seen: set[str] = set()
    for item in raw_links:
        if not isinstance(item, dict):
            continue
        href = str(item.get("href") or "").strip()
        if not href:
            continue
        if "/praca/" not in href and "/job/" not in href:
            continue
        if href in seen:
            continue
        seen.add(href)

        text = str(item.get("text") or "")
        text_lines = [line.strip() for line in text.splitlines() if line.strip()]
        candidate = _build_candidate(href, text_lines)
        if candidate:
            candidates.append(candidate)

    return candidates


def _fetch_api_with_selenium(driver: webdriver.Chrome, limit: int) -> list[dict]:
    url = THEPROTOCOL_API_URL.format(offset=0, limit=limit)
    return _fetch_api_url_with_selenium(driver, url)


def _fetch_api_url_with_selenium(driver: webdriver.Chrome, url: str) -> list[dict]:
    try:
        payload = driver.execute_script(
            """
            const url = arguments[0];
            const done = arguments[1];
            fetch(url, { credentials: 'include' })
              .then(r => r.json())
              .then(data => done({ ok: true, data }))
              .catch(err => done({ ok: false, error: String(err) }));
            """,
            url,
        )
    except Exception as exc:
        logger.debug("Selenium API fetch failed: %s", exc)
        return []

    if not isinstance(payload, dict) or not payload.get("ok"):
        logger.debug("Selenium API fetch returned no data")
        return []

    if os.environ.get("JOBPULSE_THEPROTOCOL_API_DUMP", "0").strip().lower() in {"1", "true", "yes"}:
        dump_path = os.environ.get("JOBPULSE_THEPROTOCOL_API_DUMP_PATH", "theprotocol_api_dump.json")
        try:
            with open(dump_path, "w", encoding="utf-8") as handle:
                json.dump(payload.get("data"), handle, ensure_ascii=False, indent=2)
            logger.info("Saved TheProtocol API payload to %s", dump_path)
        except Exception as exc:
            logger.warning("Failed to write API dump: %s", exc)

    return _extract_candidates_from_api(payload.get("data"))


def _discover_api_url_from_logs(driver: webdriver.Chrome) -> str | None:
    try:
        entries = driver.get_log("performance")
    except Exception as exc:
        logger.debug("Unable to read performance logs for API discovery: %s", exc)
        return None

    apus_urls: list[str] = []
    for entry in entries:
        try:
            message = json.loads(entry.get("message", "{}"))
            method = message.get("message", {}).get("method")
            params = message.get("message", {}).get("params", {})
            if method != "Network.requestWillBeSent":
                continue
            request = params.get("request", {})
            url = request.get("url")
            if not url:
                continue
            if "apus-api.theprotocol.it" in url and "/v2/recommendations" in url:
                apus_urls.append(url)
        except Exception:
            continue

    if apus_urls:
        return apus_urls[-1]
    return None


def _discover_api_url_from_dump_file() -> str | None:
    dump_path = os.environ.get("JOBPULSE_THEPROTOCOL_NET_DUMP", "theprotocol_requests.txt")
    if not os.path.exists(dump_path):
        return None

    try:
        with open(dump_path, "r", encoding="utf-8") as handle:
            lines = [line.strip() for line in handle if line.strip()]
    except OSError:
        return None

    apus_urls = [
        line
        for line in lines
        if "apus-api.theprotocol.it" in line and "/v2/recommendations" in line
    ]
    if apus_urls:
        return apus_urls[-1]
    return None


def _dump_network_requests(driver: webdriver.Chrome) -> None:
    """Dump network request URLs seen by Selenium to help find API endpoints."""
    try:
        entries = driver.get_log("performance")
    except Exception as exc:
        logger.warning("Unable to read performance logs: %s", exc)
        return

    urls: list[str] = []
    for entry in entries:
        try:
            message = json.loads(entry.get("message", "{}"))
            method = message.get("message", {}).get("method")
            params = message.get("message", {}).get("params", {})
            if method == "Network.requestWillBeSent":
                request = params.get("request", {})
                url = request.get("url")
                if url:
                    urls.append(url)
        except Exception:
            continue

    if not urls:
        logger.info("No network URLs captured in performance logs")
        return

    output_path = os.environ.get("JOBPULSE_THEPROTOCOL_NET_DUMP", "theprotocol_requests.txt")
    with open(output_path, "w", encoding="utf-8") as handle:
        for url in sorted(set(urls)):
            handle.write(url + "\n")

    logger.info("Saved %d network URLs to %s", len(set(urls)), output_path)


class TheProtocolScraper:
    """Scraper for theprotocol.it job board."""

    source = "theprotocol"

    def fetch_offers(self, limit: int = 20, timeout: int = 15) -> list[JobOffer]:
        run_start = time.perf_counter()
        logger.info("Starting TheProtocol scrape (limit=%d, timeout=%ds)", limit, timeout)

        # Try API first with requests (may work if cookies are valid)
        api_candidates = _fetch_api_with_requests(limit=limit, timeout=timeout)
        if api_candidates:
            logger.info("TheProtocol API returned %d offers", len(api_candidates))
            raw_candidates = api_candidates
            html = ""
            mode = "api"
        else:
            html, mode = _fetch_with_requests(timeout=timeout, retries=2)
            raw_candidates = []

        if html is None:
            html, mode, dom_candidates = _fetch_with_selenium(timeout=timeout)
        else:
            dom_candidates = None

        if html is None and not raw_candidates:
            logger.warning("TheProtocol scrape finished with no HTML (mode=%s)", mode)
            logger.warning(
                "If TheProtocol is challenge-protected, set JOBPULSE_THEPROTOCOL_COOKIE with browser cookies (e.g. cf_clearance=...; __cf_bm=...)"
            )
            return []

        logger.info("TheProtocol HTML acquired via mode=%s", mode)

        if not raw_candidates:
            if dom_candidates:
                raw_candidates = dom_candidates
            else:
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
