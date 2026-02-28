import json
import os
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

ENV_PREFIX = "JOBPULSE_"


class ConfigError(Exception):
    """Raised when configuration is invalid – message is user-friendly."""


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


def _apply_env_overrides(data: dict) -> dict:
    """Override config values with JOBPULSE_* environment variables.

    Supported variables:
        JOBPULSE_SOURCES              – comma-separated list of sources
        JOBPULSE_LIMIT                – integer
        JOBPULSE_DB_PATH              – string
        JOBPULSE_FILTER_MIN_SALARY_PLN – integer or empty to clear
        JOBPULSE_FILTER_CITY          – string or empty to clear
        JOBPULSE_FILTER_MUST_HAVE_SKILLS – comma-separated list
    """
    env_map: dict[str, tuple[list[str], type]] = {
        "SOURCES": (["sources"], list),
        "LIMIT": (["limit"], int),
        "DB_PATH": (["db_path"], str),
        "FILTER_MIN_SALARY_PLN": (["filters", "min_salary_pln"], int),
        "FILTER_CITY": (["filters", "city"], str),
        "FILTER_MUST_HAVE_SKILLS": (["filters", "must_have_skills"], list),
    }

    for suffix, (keys, expected_type) in env_map.items():
        env_value = os.environ.get(f"{ENV_PREFIX}{suffix}")
        if env_value is None:
            continue

        converted: object
        if expected_type is list:
            converted = [s.strip() for s in env_value.split(",") if s.strip()]
        elif expected_type is int:
            if env_value == "":
                converted = None
            else:
                try:
                    converted = int(env_value)
                except ValueError:
                    raise ConfigError(
                        f"Environment variable {ENV_PREFIX}{suffix}={env_value!r} "
                        f"must be an integer"
                    ) from None
        else:
            converted = env_value if env_value != "" else None

        # Set nested key
        target = data
        for key in keys[:-1]:
            target = target.setdefault(key, {})
        target[keys[-1]] = converted

    return data


def _format_validation_errors(exc: ValidationError) -> str:
    """Turn Pydantic ValidationError into readable bullet list."""
    lines = ["Configuration errors:"]
    for err in exc.errors():
        loc = " -> ".join(str(p) for p in err["loc"])
        msg = err["msg"]
        val = err.get("input")
        hint = f"  - {loc}: {msg}"
        if val is not None:
            hint += f" (got: {val!r})"
        lines.append(hint)
    return "\n".join(lines)


def load_config(path: str | Path = "config.json") -> AppConfig:
    config_path = Path(path)
    local_path = config_path.with_name("config.local.json")

    if not config_path.exists() and not local_path.exists():
        raw_data: dict = {}
    else:
        raw_data = {}
        if config_path.exists():
            try:
                raw_data = json.loads(config_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ConfigError(
                    f"Cannot parse {config_path}: {exc.args[0]} "
                    f"(line {exc.lineno}, col {exc.colno})"
                ) from exc
        if local_path.exists():
            try:
                local_data = json.loads(local_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ConfigError(
                    f"Cannot parse {local_path}: {exc.args[0]} "
                    f"(line {exc.lineno}, col {exc.colno})"
                ) from exc
            raw_data = _merge_dicts(raw_data, local_data)

    raw_data = _apply_env_overrides(raw_data)

    try:
        return AppConfig.model_validate(raw_data)
    except ValidationError as exc:
        raise ConfigError(_format_validation_errors(exc)) from exc
