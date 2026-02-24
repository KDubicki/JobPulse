import json
import sqlite3
from datetime import datetime
from pathlib import Path

from src.models import JobOffer


class SQLiteOfferStore:
    def __init__(self, db_path: str | Path = "jobpulse.db") -> None:
        self.db_path = str(db_path)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_offers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    city TEXT,
                    workplace_type TEXT NOT NULL,
                    employment_type TEXT,
                    salary_min_pln INTEGER,
                    salary_max_pln INTEGER,
                    currency TEXT,
                    skills TEXT,
                    offer_url TEXT NOT NULL,
                    published_at TEXT,
                    scraped_at TEXT NOT NULL,
                    UNIQUE(source, external_id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_job_offers_company
                ON job_offers(company)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_job_offers_city
                ON job_offers(city)
                """
            )

    @staticmethod
    def _serialize_skills(skills: list[str]) -> str:
        return json.dumps(skills, ensure_ascii=False)

    def save_offers(self, offers: list[JobOffer]) -> int:
        if not offers:
            return 0

        inserted = 0
        with sqlite3.connect(self.db_path) as conn:
            for offer in offers:
                try:
                    conn.execute(
                        """
                        INSERT INTO job_offers (
                            source, external_id, title, company, city, workplace_type,
                            employment_type, salary_min_pln, salary_max_pln, currency,
                            skills, offer_url, published_at, scraped_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            offer.source,
                            offer.external_id,
                            offer.title,
                            offer.company,
                            offer.city,
                            offer.workplace_type,
                            offer.employment_type,
                            offer.salary_min_pln,
                            offer.salary_max_pln,
                            offer.currency,
                            self._serialize_skills(offer.skills),
                            str(offer.offer_url),
                            offer.published_at.isoformat() if offer.published_at else None,
                            offer.scraped_at.isoformat() if isinstance(offer.scraped_at, datetime) else datetime.utcnow().isoformat(),
                        ),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    continue
        return inserted
