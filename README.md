# JobPulse ⚡

JobPulse is a work-in-progress smart job aggregator and notification system. The goal of this project is to monitor the IT job market, classify offers, and deliver personalized alerts directly to users via Telegram.

## 🎯 Project Goals (Assumptions)

1. **Multi-Source Aggregation:** Fetch job listings from various Polish IT job boards (e.g., JustJoinIT, theprotocol).
2. **Data Normalization & Classification:** Clean up the raw data, extract key information (tech stack, salary, remote/office), and unify it into a single format.
3. **Custom Configurations:** Allow multiple users (friends) to set up their own specific filters (e.g., "Python, B2B, >15k PLN, 100% Remote").
4. **Real-Time Notifications:** Send matching job offers directly to users through a Telegram Bot as soon as they are published.

## 🛠️ Base Tech Stack

This is the foundational stack planned for the initial development phase:

* **Language:** Python 3.11+
* **Data Validation:** `pydantic` (for a unified job offer schema)
* **Web Scraping:** `requests` / `playwright` / `BeautifulSoup` (depending on the target site's protections)
* **Telegram Bot:** `aiogram` (for asynchronous bot interactions)
* **Database:** SQLite (for local development) migrating to PostgreSQL later

## 📝 Next Steps (Initial Phase)

- [ ] Initialize the project and define the folder structure.
- [ ] Create a unified Pydantic model for a `JobOffer`.
- [ ] Write the first proof-of-concept scraper for a single website.
- [ ] Set up a basic Telegram bot that can echo messages.