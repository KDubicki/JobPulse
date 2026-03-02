import argparse
import logging
import sys

from src.config import AppConfig, ConfigError, load_config
from src.filters import OfferFilter, filter_offers
from src.logger import setup_logging
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
    return parser.parse_args()


def main() -> None:
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

    logger.info("Starting JobPulse with sources=%s, limit=%d", config.sources, config.limit)
    
    scrapers = get_scrapers(config.sources)
    if not scrapers:
        logger.warning("No valid scrapers enabled. Check your config/sources.")
        return

    offers = []
    for scraper in scrapers:
        offers.extend(scraper.fetch_offers(limit=config.limit))

    offer_filter = OfferFilter(
        min_salary_pln=config.filters.min_salary_pln,
        city=config.filters.city,
        must_have_skills=config.filters.must_have_skills,
    )
    filtered_offers = filter_offers(offers, offer_filter)
    store = SQLiteOfferStore(db_path=config.db_path)
    inserted = store.save_offers(filtered_offers)

    print(f"\n[SUMMARY]")
    print(f"Fetched: {len(offers)}")
    print(f"Filtered: {len(filtered_offers)}")
    print(f"New saved: {inserted}")
    print("-" * 40)
    
    for index, offer in enumerate(filtered_offers, start=1):
        salary = _format_salary(offer.salary_min_pln, offer.salary_max_pln)
        skills_preview = ", ".join(offer.skills[:4]) if offer.skills else "brak"
        print(
            f"{index}. {offer.title} | {offer.company} | {offer.city or '?'} | "
            f"salary: {salary} | skills: {skills_preview}"
        )


if __name__ == "__main__":
    main()
