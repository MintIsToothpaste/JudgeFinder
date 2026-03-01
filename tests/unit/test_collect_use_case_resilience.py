from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from judgefinder.application.use_cases import CollectNoticesUseCase
from judgefinder.domain.entities import Notice, SourceType


@dataclass(slots=True)
class StubRepository:
    saved_notices: list[Notice]

    def save_many(self, notices: list[Notice]) -> None:
        self.saved_notices = list(notices)


@dataclass(slots=True)
class HealthySource:
    slug: str
    notice: Notice

    def fetch(self, target_date: date) -> list[Notice]:
        _ = target_date
        return [self.notice]


@dataclass(slots=True)
class FailingSource:
    slug: str

    def fetch(self, target_date: date) -> list[Notice]:
        _ = target_date
        raise RuntimeError("temporary network failure")


def test_collect_use_case_skips_failed_source_and_continues() -> None:
    fetched_at = datetime(2026, 3, 1, 18, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    target_date = date(2026, 2, 2)
    notice = Notice(
        id=None,
        municipality="테스트시",
        title="평가위원 모집 공고",
        url="https://example.go.kr/notice/1",
        published_date=target_date,
        fetched_at=fetched_at,
        source_type=SourceType.HTML,
    )

    repository = StubRepository(saved_notices=[])
    use_case = CollectNoticesUseCase(
        repository=repository,
        sources=[
            FailingSource(slug="failing"),
            HealthySource(slug="healthy", notice=notice),
        ],
    )

    collected = use_case.execute(target_date)

    assert len(collected) == 1
    assert collected[0].url == notice.url
    assert len(repository.saved_notices) == 1
    assert repository.saved_notices[0].url == notice.url
