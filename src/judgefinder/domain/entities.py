from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class SourceType(str, Enum):
    HTML = "html"
    API = "api"


@dataclass(slots=True)
class Notice:
    id: int | None
    municipality: str
    title: str
    url: str
    published_date: date
    fetched_at: datetime
    source_type: SourceType

    @property
    def unique_key(self) -> tuple[str, str]:
        return (self.municipality, self.url)
