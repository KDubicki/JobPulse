import json
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError


class FilterConfig(BaseModel):
    min_salary_pln: int | None = None
    city: str | None = None
    must_have_skills: list[str] = Field(default_factory=list)


class AppConfig(BaseModel):
    sources: list[str] = Field(default_factory=lambda: ["justjoinit"])
    limit: int = 30
    db_path: str = "jobpulse.db"
    filters: FilterConfig = Field(default_factory=FilterConfig)


def load_config(path: str | Path = "config.json") -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        return AppConfig()

    raw_data = json.loads(config_path.read_text(encoding="utf-8"))
    try:
        return AppConfig.model_validate(raw_data)
    except ValidationError as exc:
        raise ValueError(f"Invalid config: {exc}") from exc
