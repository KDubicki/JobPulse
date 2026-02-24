from src.config import load_config
from src.filters import OfferFilter, filter_offers
from src.scrapers import JustJoinItScraper
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
	config = load_config()
	limit = int(config.get("limit", 30))
	db_path = config.get("db_path", "jobpulse.db")
	filters = config.get("filters", {}) or {}

	scraper = JustJoinItScraper()
	offers = scraper.fetch_offers(limit=limit)

	offer_filter = OfferFilter(
		min_salary_pln=filters.get("min_salary_pln"),
		city=filters.get("city"),
		must_have_skills=filters.get("must_have_skills"),
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
