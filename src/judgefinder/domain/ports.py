from __future__ import annotations

from datetime import date
from typing import Protocol

from judgefinder.domain.entities import Notice


class NoticeRepository(Protocol):
    def save_many(self, notices: list[Notice]) -> None:
        ...

    def list_by_date(self, target_date: date) -> list[Notice]:
        ...


class NoticeSource(Protocol):
    slug: str

    def fetch(self, target_date: date) -> list[Notice]:
        ...
