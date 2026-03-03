import logging

from src.models import JobOffer

logger = logging.getLogger(__name__)

THEPROTOCOL_OFFERS_URL = "https://theprotocol.it/praca"


class TheProtocolScraper:
    """Skeleton scraper for theprotocol.it source.

    Full extraction and field mapping are added in next steps.
    """

    source = "theprotocol"

    def fetch_offers(self, limit: int = 20, timeout: int = 15) -> list[JobOffer]:
        logger.info(
            "TheProtocol scraper skeleton invoked (limit=%d, timeout=%ds)",
            limit,
            timeout,
        )
        logger.warning(
            "TheProtocol scraper is not fully implemented yet. Returning no offers."
        )
        return []
