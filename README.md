# JobPulse ⚡

JobPulse is a work-in-progress smart job aggregator and notification system.
The project monitors IT job boards, normalizes offers into a shared data model,
and will deliver personalized alerts via Telegram.

## 🎯 Project Goals

1. **Multi-Source Aggregation:** Fetch job listings from various Polish IT job boards (e.g., JustJoinIT, theprotocol).
2. **Data Normalization:** Extract key attributes (title, company, city, salary, skills, workplace type) into one schema.
3. **User-Specific Filtering:** Support per-user preferences (e.g., "Python, B2B, >15k PLN, 100% Remote").
4. **Real-Time Notifications:** Send matching offers to users through a Telegram Bot.

## ✅ Current Project Status

The initial proof-of-concept is implemented.

### Implemented

- Project skeleton and package structure (`src/models`, `src/scrapers`, `main.py`)
- Unified `JobOffer` data model using Pydantic
- First JustJoinIT scraper (Selenium-based)
- Basic pipeline in `main.py`:
  - fetch offers
  - map to `JobOffer`
  - print a compact console preview
- Basic project configuration (`.gitignore`, `requirements.txt`)

### Current Scope of Data Mapping

- Strongly mapped: `title`, `company`, `city`, `salary_min_pln`, `salary_max_pln`, `skills`
- Available with partial coverage on listing cards: `workplace_type`, `employment_type`

## 🛠️ Tech Stack

Current stack used in the repository:

* **Language:** Python 3.11+
* **Data Model & Validation:** `pydantic`
* **Web Scraping:** `selenium` (current POC), `requests` / `BeautifulSoup` for future sources where applicable
* **Bot Layer (planned next phase):** `aiogram`
* **Persistence (planned next phase):** SQLite first, PostgreSQL later

## 🗂️ Project Structure

```
.
├── main.py
├── requirements.txt
├── src
│   ├── models
│   │   ├── __init__.py
│   │   └── job_offer.py
│   └── scrapers
│       ├── __init__.py
│       └── justjoinit.py
└── TASKS.md
```

## ▶️ Run Locally

```bash
pip install -r requirements.txt
python main.py
```

## 📝 Next Steps

1. **Improve field completeness**
	- Add optional detail-page enrichment for `workplace_type`, `employment_type`, and richer salary metadata.

2. **Add persistence layer**
	- Save normalized offers in SQLite.
	- Add deduplication by `source + external_id`.

3. **Introduce source abstraction**
	- Define a common scraper interface.
	- Prepare onboarding for additional sources (e.g., theprotocol).

4. **Add Telegram bot MVP**
	- Create a basic bot command set.
	- Send latest matching offers for a simple user profile.

5. **Add filtering and user configuration**
	- Introduce per-user filters (tech, salary threshold, remote preference, contract type).

6. **Add scheduling and automation**
	- Run scraping on interval.
	- Process only new offers and trigger notifications.
