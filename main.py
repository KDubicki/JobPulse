import argparse
import csv
import json
import logging
import os
import sys
import time
from pathlib import Path

from src.config import AppConfig, ConfigError, load_config
from src.filters import OfferFilter, filter_offers
from src.logger import setup_logging
from src.models import JobOffer
from src.scrapers import get_scrapers
from src.storage import SQLiteOfferStore

logger = logging.getLogger(__name__)


def _format_salary(salary_min_pln: int | None, salary_max_pln: int | None) -> str:
    if salary_min_pln is None and salary_max_pln is None:
        return "brak"
    if salary_min_pln is not None and salary_max_pln is not None:
        return f"{salary_min_pln} - {salary_max_pln} PLN"
    if salary_min_pln is not None:
        return f"od {salary_min_pln} PLN"
    return f"do {salary_max_pln} PLN"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JobPulse – Smart Job Aggregator")
    parser.add_argument(
        "--sources",
        help="Comma-separated list of sources to scrape (overrides config)",
    )
    parser.add_argument(
        "-n", "--limit", type=int, help="Limit offers per source (overrides config)"
    )
    parser.add_argument(
        "--city", help="Filter by city (overrides config filter)"
    )
    parser.add_argument(
        "--min-salary", type=int, help="Filter by min salary (overrides config filter)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without saving to database (useful for testing)",
    )
    parser.add_argument(
        "--output",
        help="Export filtered offers to a file (.csv or .json)",
    )
    parser.add_argument(
        "--cache-path",
        default=".jobpulse_cache.json",
        help="Path to cache file (default: .jobpulse_cache.json)",
    )
    parser.add_argument(
        "--cache-ttl",
        type=int,
        default=0,
        help="Cache TTL in seconds (0 disables cache)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable cache even if TTL is set",
    )
    return parser.parse_args()


def _offer_to_export_row(offer: "JobOffer") -> dict:
    return {
        "source": offer.source,
        "external_id": offer.external_id,
        "title": offer.title,
        "company": offer.company,
        "city": offer.city,
        "workplace_type": offer.workplace_type,
        "employment_type": offer.employment_type,
        "salary_min_pln": offer.salary_min_pln,
        "salary_max_pln": offer.salary_max_pln,
        "currency": offer.currency,
        "skills": ", ".join(offer.skills),
        "offer_url": str(offer.offer_url),
        "published_at": offer.published_at.isoformat() if offer.published_at else None,
        "scraped_at": offer.scraped_at.isoformat(),
    }


def _export_offers(offers: list["JobOffer"], output_path: str) -> None:
    if output_path.lower().endswith(".json"):
        data = [_offer_to_export_row(offer) for offer in offers]
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        logger.info("Exported %d offers to %s", len(offers), output_path)
        return

    if output_path.lower().endswith(".csv"):
        data = [_offer_to_export_row(offer) for offer in offers]
        if not data:
            logger.warning("No offers to export (CSV)")
            return
        with open(output_path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(data[0].keys()))
            writer.writeheader()
            writer.writerows(data)
        logger.info("Exported %d offers to %s", len(offers), output_path)
        return

    logger.error("Unsupported output format for %s (use .csv or .json)", output_path)


def _load_cache(cache_path: Path) -> dict:
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to read cache file: %s", cache_path)
        return {}


def _save_cache(cache_path: Path, payload: dict) -> None:
    try:
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to write cache file %s: %s", cache_path, exc)


def _offers_to_cache_payload(offers: list["JobOffer"]) -> list[dict]:
    return [offer.model_dump(mode="json") for offer in offers]


def _offers_from_cache_payload(payload: list[dict]) -> list["JobOffer"]:
    return [JobOffer.model_validate(item) for item in payload]


def _should_use_cache(cache_entry: dict, ttl: int) -> bool:
    if ttl <= 0:
        return False
    ts = cache_entry.get("ts")
    if not isinstance(ts, (int, float)):
        return False
    age = time.time() - ts
    return age <= ttl


def main() -> None:
    start_time = time.time()
    setup_logging()
    args = parse_args()

    try:
        config = load_config()
    except ConfigError as exc:
        print(f"[config error] {exc}", file=sys.stderr)
        sys.exit(1)

    # CLI args override config
    if args.limit:
        config.limit = args.limit
    if args.sources:
        config.sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    if args.city:
        config.filters.city = args.city
    if args.min_salary:
        config.filters.min_salary_pln = args.min_salary

    logger.info("Starting JobPulse (dry-run=%s) sources=%s limit=%d", args.dry_run, config.sources, config.limit)
    
    scrapers = get_scrapers(config.sources)
    if not scrapers:
        logger.warning("No valid scrapers enabled. Check your config/sources.")
        return

    cache_path = Path(args.cache_path)
    cache_data = _load_cache(cache_path)

    offers = []
    for scraper in scrapers:
        cache_key = f"{scraper.source}:{config.limit}"
        cache_entry = cache_data.get(cache_key) if isinstance(cache_data, dict) else None
        if not args.no_cache and _should_use_cache(cache_entry or {}, args.cache_ttl):
            logger.info("Cache hit for %s (ttl=%ss)", cache_key, args.cache_ttl)
            cached_offers = _offers_from_cache_payload(cache_entry.get("offers", []))
            offers.extend(cached_offers)
            continue

        fresh_offers = scraper.fetch_offers(limit=config.limit)
        offers.extend(fresh_offers)

        if args.cache_ttl > 0 and not args.no_cache:
            cache_data[cache_key] = {
                "ts": time.time(),
                "offers": _offers_to_cache_payload(fresh_offers),
            }

    if args.cache_ttl > 0 and not args.no_cache:
        _save_cache(cache_path, cache_data)

    offer_filter = OfferFilter(
        min_salary_pln=config.filters.min_salary_pln,
        city=config.filters.city,
        must_have_skills=config.filters.must_have_skills,
    )
    filtered_offers = filter_offers(offers, offer_filter)

    if args.output:
        _export_offers(filtered_offers, args.output)

    inserted = 0
    if not args.dry_run:
        store = SQLiteOfferStore(db_path=config.db_path)
        inserted = store.save_offers(filtered_offers)
    else:
        logger.info("Dry-run enabled: skipping DB save")

    duration = time.time() - start_time
    
    # Run Summary
    print("\n" + "=" * 50)
    print("JOBPULSE RUN SUMMARY")
    print("=" * 50)
    print(f"Total time:       {duration:.2f}s")
    print(f"Total sources:    {len(config.sources)}")
    print(f"Offers fetched:   {len(offers)}")
    print(f"Offers matched:   {len(filtered_offers)}")
    print(f"New saved:        {inserted} {'(dry-run)' if args.dry_run else ''}")
    print("-" * 50)

    for index, offer in enumerate(filtered_offers, start=1):
        salary = _format_salary(offer.salary_min_pln, offer.salary_max_pln)
        skills_preview = ", ".join(offer.skills[:4]) if offer.skills else "brak"
        print(
            f"{index}. {offer.title} | {offer.company} | {offer.city or '?'} | "
            f"salary: {salary} | skills: {skills_preview}"
        )
    print("=" * 50)


if __name__ == "__main__":
    main()
