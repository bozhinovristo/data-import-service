from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, HttpUrl, field_validator


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
