from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from judgefinder.adapters.sources.sample_city.parser import parse_sample_city_notices
from judgefinder.domain.entities import SourceType


def test_parse_sample_city_notices_filters_by_target_date() -> None:
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "sample_city_list.html"
    html = fixture_path.read_text(encoding="utf-8")
    fetched_at = datetime(2026, 2, 16, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))

    notices = parse_sample_city_notices(
        html,
        municipality="샘플시",
        list_url="https://example.com/sample_city/notices",
        target_date=date(2026, 2, 16),
        fetched_at=fetched_at,
        source_type=SourceType.HTML,
    )

    assert len(notices) == 2
    assert [notice.title for notice in notices] == ["평가위원 모집 공고 A", "평가위원 모집 공고 B"]
    assert [notice.url for notice in notices] == [
        "https://example.com/sample-city/notices/20260216-a",
        "https://example.com/sample-city/notices/20260216-b",
    ]
