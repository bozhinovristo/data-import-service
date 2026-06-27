import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    HttpUrl,
    field_validator,
    model_validator,
)

logger = logging.getLogger(__name__)


class Employee(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    date_of_birth: date
    image: HttpUrl
    email: EmailStr
    first_name: str
    last_name: str
    title: str
    address: str
    country: str
    bio: str
    rating: float
    fetched_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def _log_unknown_fields(cls, data: Any) -> Any:
        """Warn about unknown fields before they are dropped by extra='ignore'.

        The spec requires unknown fields to be tolerated *and logged* so they
        stay traceable. We log here rather than crashing, then let validation
        proceed (the extras are silently ignored by the model config).
        """
        if isinstance(data, dict):
            unknown = set(data) - set(cls.model_fields)
            if unknown:
                logger.warning(
                    "Employee id=%s has unknown field(s) ignored: %s",
                    data.get("id", "<unknown>"),
                    ", ".join(sorted(unknown)),
                )
        return data

    @field_validator("rating", mode="before")
    @classmethod
    def parse_rating(cls, v: str | float) -> float:
        return float(v)


@dataclass
class EmployeeRow:
    """DB row representation returned from database queries."""

    id: str
    date_of_birth: str
    image: str
    email: str
    first_name: str
    last_name: str
    title: str
    address: str
    country: str
    bio: str
    rating: float
    fetched_at: str
