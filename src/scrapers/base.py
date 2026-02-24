from typing import Protocol

from src.models import JobOffer


class JobScraper(Protocol):
    source: str

    def fetch_offers(self, limit: int = 20, timeout: int = 15) -> list[JobOffer]:
        ...
