from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from judgefinder.domain.entities import Notice
from judgefinder.domain.ports import NoticeRepository, NoticeSource


class CollectNoticesUseCase:
    def __init__(self, repository: NoticeRepository, sources: Sequence[NoticeSource]) -> None:
        self._repository = repository
        self._sources = list(sources)

    def execute(self, target_date: date) -> list[Notice]:
        notices: list[Notice] = []
        seen_keys: set[tuple[str, str]] = set()

        for source in self._sources:
            for notice in source.fetch(target_date):
                if notice.unique_key in seen_keys:
                    continue
                seen_keys.add(notice.unique_key)
                notices.append(notice)

        self._repository.save_many(notices)
        return notices


class ListNoticesUseCase:
    def __init__(self, repository: NoticeRepository) -> None:
        self._repository = repository

    def execute(self, target_date: date) -> list[Notice]:
        return self._repository.list_by_date(target_date)
