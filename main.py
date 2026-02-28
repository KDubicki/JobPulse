import sys

from src.config import ConfigError, load_config
from src.filters import OfferFilter, filter_offers
from src.scrapers import get_scrapers
from src.storage import SQLiteOfferStore


def _format_salary(salary_min_pln: int | None, salary_max_pln: int | None) -> str:
	if salary_min_pln is None and salary_max_pln is None:
		return "brak"
	if salary_min_pln is not None and salary_max_pln is not None:
		return f"{salary_min_pln} - {salary_max_pln} PLN"
	if salary_min_pln is not None:
		return f"od {salary_min_pln} PLN"
	return f"do {salary_max_pln} PLN"


def main() -> None:
	try:
		config = load_config()
	except ConfigError as exc:
		print(f"[config error] {exc}", file=sys.stderr)
		sys.exit(1)
	limit = config.limit
	db_path = config.db_path
	filters = config.filters

	scrapers = get_scrapers(config.sources)
	offers = []
	for scraper in scrapers:
		offers.extend(scraper.fetch_offers(limit=limit))

	offer_filter = OfferFilter(
		min_salary_pln=filters.min_salary_pln,
		city=filters.city,
		must_have_skills=filters.must_have_skills,
	)
	filtered_offers = filter_offers(offers, offer_filter)
	store = SQLiteOfferStore(db_path=db_path)
	inserted = store.save_offers(filtered_offers)

	print(f"Pobrano ofert: {len(offers)}")
	print(f"Po filtrach: {len(filtered_offers)}")
	print(f"Zapisano nowych ofert: {inserted}")
	for index, offer in enumerate(filtered_offers, start=1):
		salary = _format_salary(offer.salary_min_pln, offer.salary_max_pln)
		skills_preview = ", ".join(offer.skills[:4]) if offer.skills else "brak"
		print(
			f"{index}. {offer.title} | {offer.company} | {offer.workplace_type} | "
			f"salary: {salary} | skills: {skills_preview}"
		)


if __name__ == "__main__":
	main()
