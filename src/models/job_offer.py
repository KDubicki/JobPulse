from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class JobOffer(BaseModel):
    source: Literal["justjoinit", "theprotocol", "other"] = "justjoinit"
    external_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    company: str = Field(..., min_length=1)
    city: str | None = None
    workplace_type: Literal["remote", "hybrid", "office", "unknown"] = "unknown"
    employment_type: str | None = None
    salary_min_pln: int | None = Field(default=None, ge=0)
    salary_max_pln: int | None = Field(default=None, ge=0)
    currency: str | None = "PLN"
    skills: list[str] = Field(default_factory=list)
    offer_url: HttpUrl
    published_at: datetime | None = None
    scraped_at: datetime = Field(default_factory=datetime.utcnow)