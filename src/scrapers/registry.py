from src.scrapers import JobScraper, JustJoinItScraper, TheProtocolScraper


def get_scrapers(sources: list[str]) -> list[JobScraper]:
    available = {
        "justjoinit": JustJoinItScraper,
        "theprotocol": TheProtocolScraper,
    }

    scrapers: list[JobScraper] = []
    for source in sources:
        scraper_cls = available.get(source)
        if scraper_cls:
            scrapers.append(scraper_cls())

    return scrapers
