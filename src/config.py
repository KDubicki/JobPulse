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


def _merge_dicts(base: dict, overrides: dict) -> dict:
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str | Path = "config.json") -> AppConfig:
    config_path = Path(path)
    local_path = config_path.with_name("config.local.json")

    if not config_path.exists() and not local_path.exists():
        return AppConfig()

    raw_data: dict = {}
    if config_path.exists():
        raw_data = json.loads(config_path.read_text(encoding="utf-8"))
    if local_path.exists():
        local_data = json.loads(local_path.read_text(encoding="utf-8"))
        raw_data = _merge_dicts(raw_data, local_data)
    try:
        return AppConfig.model_validate(raw_data)
    except ValidationError as exc:
        raise ValueError(f"Invalid config: {exc}") from exc
