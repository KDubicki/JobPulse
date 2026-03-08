from dataclasses import dataclass
import re

from src.models import JobOffer


@dataclass
class OfferFilter:
    min_salary_pln: int | None = None
    city: str | None = None
    must_have_skills: list[str] | None = None
    skills_match: str = "all"  # "all" or "any"
    title_regex: str | None = None
    workplace_type: str | None = None

    def matches(self, offer: JobOffer) -> bool:
        if self.min_salary_pln is not None:
            salary_floor = offer.salary_min_pln
            if salary_floor is None:
                salary_floor = offer.salary_max_pln
            if salary_floor is None or salary_floor < self.min_salary_pln:
                return False

        if self.city:
            if not offer.city or offer.city.lower() != self.city.lower():
                return False

        if self.workplace_type:
            if offer.workplace_type.lower() != self.workplace_type.lower():
                return False

        if self.must_have_skills:
            normalized = {_normalize_skill(skill) for skill in offer.skills}
            required_set = {_normalize_skill(required) for required in self.must_have_skills}
            if self.skills_match == "any":
                if not (normalized & required_set):
                    return False
            else:
                for required in required_set:
                    if required not in normalized:
                        return False

        if self.title_regex:
            if not re.search(self.title_regex, offer.title, flags=re.IGNORECASE):
                return False

        return True


def filter_offers(offers: list[JobOffer], offer_filter: OfferFilter) -> list[JobOffer]:
    return [offer for offer in offers if offer_filter.matches(offer)]


def _normalize_skill(skill: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", skill.lower()).strip()
    return " ".join(cleaned.split())
