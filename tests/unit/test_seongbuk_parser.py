from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from judgefinder.adapters.sources.seongbuk.parser import parse_seongbuk_notices
from judgefinder.domain.entities import SourceType


def test_parse_seongbuk_notices_filters_by_date_and_keywords() -> None:
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "seongbuk_rss.xml"
    rss_xml = fixture_path.read_text(encoding="utf-8")
    fetched_at = datetime(2026, 2, 16, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))

    notices = parse_seongbuk_notices(
        rss_xml,
        municipality="성북구",
        list_url="https://www.sb.go.kr/www/gosiToRss.do",
        target_date=date(2026, 2, 16),
        fetched_at=fetched_at,
        source_type=SourceType.API,
    )

    assert len(notices) == 2
    assert [notice.title for notice in notices] == [
        "제안서 평가위원(후보자) 공개모집 공고",
        "정비사업 용역 공고",
    ]
    assert [notice.url for notice in notices] == [
        "https://www.sb.go.kr/www/notice/1001",
        "https://www.sb.go.kr/www/notice/1002",
    ]
    assert all(notice.published_date == date(2026, 2, 16) for notice in notices)
    assert all(notice.source_type == SourceType.API for notice in notices)


def test_parse_seongbuk_notices_supports_numeric_regdate_format() -> None:
    rss_xml = """
<rss version="2.0">
  <channel>
    <item>
      <title>용역 제안서 평가위원(후보자) 모집 공고</title>
      <regdate>202602161230</regdate>
      <link>https://www.sb.go.kr/www/notice/2001</link>
    </item>
  </channel>
</rss>
"""
    fetched_at = datetime(2026, 2, 16, 12, 40, tzinfo=ZoneInfo("Asia/Seoul"))

    notices = parse_seongbuk_notices(
        rss_xml,
        municipality="성북구",
        list_url="https://www.sb.go.kr/www/gosiToRss.do",
        target_date=date(2026, 2, 16),
        fetched_at=fetched_at,
        source_type=SourceType.API,
    )

    assert len(notices) == 1
    assert notices[0].url == "https://www.sb.go.kr/www/notice/2001"
