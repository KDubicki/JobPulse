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
- Scraper interface and class-based source integration
- Basic pipeline in `main.py`:
	- fetch offers
	- map to `JobOffer`
	- apply filters
	- store in SQLite
	- print a compact console preview
- Local SQLite storage with deduplication (`source + external_id`)
- Config file for runtime settings (`config.json`)
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
* **Persistence:** SQLite (current), PostgreSQL later

## 🗂️ Project Structure

```
.
├── main.py
├── config.json
├── requirements.txt
├── src
│   ├── config.py
│   ├── filters
│   │   ├── __init__.py
│   │   └── simple_filter.py
│   ├── models
│   │   ├── __init__.py
│   │   └── job_offer.py
│   └── scrapers
│       ├── __init__.py
│       ├── base.py
│       └── justjoinit.py
│   └── storage
│       ├── __init__.py
│       └── sqlite_store.py
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

2. **Validate configuration**
	- Add config validation with `pydantic`.
	- Support environment-specific overrides (e.g., `config.local.json`).

3. **Expand sources**
	- Add a scraper registry and plug in additional sources (e.g., theprotocol).

4. **Add Telegram bot MVP**
	- Create a basic bot command set.
	- Send latest matching offers for a simple user profile.

5. **Enhance filtering**
	- Add per-user filters (tech, salary threshold, remote preference, contract type).
	- Add fuzzy matching for skills.

