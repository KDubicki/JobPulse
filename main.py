from src.scrapers import fetch_justjoinit_offers


def _format_salary(salary_min_pln: int | None, salary_max_pln: int | None) -> str:
	if salary_min_pln is None and salary_max_pln is None:
		return "brak"
	if salary_min_pln is not None and salary_max_pln is not None:
		return f"{salary_min_pln} - {salary_max_pln} PLN"
	if salary_min_pln is not None:
		return f"od {salary_min_pln} PLN"
	return f"do {salary_max_pln} PLN"


def main() -> None:
	offers = fetch_justjoinit_offers(limit=10)

	print(f"Pobrano ofert: {len(offers)}")
	for index, offer in enumerate(offers, start=1):
		salary = _format_salary(offer.salary_min_pln, offer.salary_max_pln)
		skills_preview = ", ".join(offer.skills[:4]) if offer.skills else "brak"
		print(
			f"{index}. {offer.title} | {offer.company} | {offer.workplace_type} | "
			f"salary: {salary} | skills: {skills_preview}"
		)


if __name__ == "__main__":
	main()
