from dataclasses import dataclass

from src.models import JobOffer


@dataclass
class OfferFilter:
    min_salary_pln: int | None = None
    city: str | None = None
    must_have_skills: list[str] | None = None

    def matches(self, offer: JobOffer) -> bool:
        if self.min_salary_pln is not None:
            if offer.salary_min_pln is None or offer.salary_min_pln < self.min_salary_pln:
                return False

        if self.city:
            if not offer.city or offer.city.lower() != self.city.lower():
                return False

        if self.must_have_skills:
            normalized = {skill.lower() for skill in offer.skills}
            for required in self.must_have_skills:
                if required.lower() not in normalized:
                    return False

        return True


def filter_offers(offers: list[JobOffer], offer_filter: OfferFilter) -> list[JobOffer]:
    return [offer for offer in offers if offer_filter.matches(offer)]
