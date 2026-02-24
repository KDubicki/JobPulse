import json
from pathlib import Path


def load_config(path: str | Path = "config.json") -> dict:
    config_path = Path(path)
    if not config_path.exists():
        return {
            "sources": ["justjoinit"],
            "limit": 30,
            "db_path": "jobpulse.db",
            "filters": {
                "min_salary_pln": 12000,
                "city": None,
                "must_have_skills": ["python"],
            },
        }

    return json.loads(config_path.read_text(encoding="utf-8"))
