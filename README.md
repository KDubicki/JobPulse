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
- Scraper registry driven by `config.json` sources
- Basic pipeline in `main.py`:
	- fetch offers
	- map to `JobOffer`
	- apply filters
	- store in SQLite
	- print a compact console preview
- Local SQLite storage with deduplication (`source + external_id`)
- Config file for runtime settings with Pydantic validation (`config.json`)
- DB viewer utility (`scripts/show_db.py`)
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
├── scripts
│   └── show_db.py
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
│       ├── registry.py
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

## ⚙️ Configuration

JobPulse loads configuration from three layers (each overrides the previous):

1. **`config.json`** – base configuration (tracked in git)
2. **`config.local.json`** – personal overrides (gitignored, same schema)
3. **Environment variables** – highest priority, ideal for CI/Docker

### config.json reference

```jsonc
{
  "sources": ["justjoinit"],   // scraper sources to run
  "limit": 30,                 // max offers per source
  "db_path": "jobpulse.db",   // SQLite database path
  "filters": {
    "min_salary_pln": null,    // minimum salary (int or null)
    "city": null,              // city name (string or null)
    "must_have_skills": []     // required skills, e.g. ["Python", "Docker"]
  }
}
```

### config.local.json

Create `config.local.json` next to `config.json` to override any subset of keys
without modifying the base file. Only the keys you specify are merged:

```json
{
  "limit": 10,
  "filters": {
    "city": "Warszawa"
  }
}
```

This file is listed in `.gitignore` and should not be committed.

### Environment variables

Any config key can be overridden with a `JOBPULSE_` prefixed env var.
Nested filter keys use `JOBPULSE_FILTER_` prefix. Lists are comma-separated.

| Variable | Type | Example |
|---|---|---|
| `JOBPULSE_SOURCES` | comma-separated list | `justjoinit,nofluffjobs` |
| `JOBPULSE_LIMIT` | integer | `50` |
| `JOBPULSE_DB_PATH` | string | `/tmp/jobs.db` |
| `JOBPULSE_FILTER_MIN_SALARY_PLN` | integer or empty | `15000` |
| `JOBPULSE_FILTER_CITY` | string or empty | `Kraków` |
| `JOBPULSE_FILTER_MUST_HAVE_SKILLS` | comma-separated list | `Python,Docker` |

Set a variable to an empty string to clear a nullable field (e.g. `JOBPULSE_FILTER_CITY=`).

### Error handling

If configuration is invalid, JobPulse prints a clear error and exits:

```
[config error] Configuration errors:
  - limit: Input should be a valid integer, unable to parse string as an integer (got: 'abc')
```

```
[config error] Cannot parse config.json: Illegal trailing comma ... (line 1, col 13)
```

```
[config error] Environment variable JOBPULSE_LIMIT='notanumber' must be an integer
```

## � DB Viewer (`scripts/show_db.py`)

Query stored offers from the command line.

### Basic usage

```bash
python scripts/show_db.py              # last 20 offers
python scripts/show_db.py -n 50        # last 50 offers
python scripts/show_db.py -v           # verbose (show skills + URL)
```

### Filtering

```bash
python scripts/show_db.py --city Warszawa
python scripts/show_db.py --company SCALO --min-salary 15000
python scripts/show_db.py --skill Python --title Engineer
python scripts/show_db.py --source justjoinit
```

All text filters use substring matching (case-insensitive in SQLite default).
`--min-salary` checks both `salary_min_pln` and `salary_max_pln`.

### Output formats (`-f`)

| Format | Flag | Description |
|--------|------|-------------|
| text   | `-f text` (default) | Human-readable, supports `-v` for details |
| table  | `-f table` | Aligned columns (title, company, city, salary, source) |
| csv    | `-f csv` | CSV to stdout — pipe to file or other tools |
| json   | `-f json` | JSON array with deserialized skills list |

```bash
python scripts/show_db.py -f csv > export.csv
python scripts/show_db.py -f json --city Kraków | jq '.[].title'
python scripts/show_db.py -f table --min-salary 20000 -n 10
```

### All options

```
--db PATH        SQLite database path (default: jobpulse.db)
-n, --limit N    Max rows (default: 20)
--city TEXT       Filter by city
--company TEXT    Filter by company
--skill TEXT      Filter by skill name
--title TEXT      Filter by title
--source TEXT     Filter by source (exact match)
--min-salary N   Minimum salary in PLN
-v, --verbose    Show skills and URL (text format only)
-f, --format     Output format: text | table | csv | json
```

## �📝 Next Steps

1. **Improve field completeness**
	- Add optional detail-page enrichment for `workplace_type`, `employment_type`, and richer salary metadata.

2. **Expand sources**
	- Plug in additional sources (e.g., theprotocol).
	- Normalize source-specific fields into the shared model.

4. **Add Telegram bot MVP**
	- Create a basic bot command set.
	- Send latest matching offers for a simple user profile.

5. **Enhance filtering**
	- Add per-user filters (tech, salary threshold, remote preference, contract type).
	- Add fuzzy matching for skills.
	- Add optional use of `salary_max_pln` for low-data offers.

