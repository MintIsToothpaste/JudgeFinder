from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from judgefinder.adapters.sources.municipal_rss.parser import parse_municipal_rss_notices
from judgefinder.domain.entities import SourceType


@pytest.mark.parametrize(
    (
        "fixture_name",
        "municipality",
        "list_url",
        "target_date",
        "expected_title",
        "expected_url",
    ),
    [
        (
            "hanam_rss.xml",
            "하남시",
            "https://www.hanam.go.kr/rssBbsNtt.do?bbsNo=31",
            date(2015, 8, 27),
            "하남시 제안서 평가위원 후보자 모집 공고",
            "https://www.hanam.go.kr/www/selectBbsNttView.do?bbsNo=31&nttNo=3101",
        ),
        (
            "pocheon_rss.xml",
            "포천시",
            "https://www.pocheon.go.kr/rssBbsNtt.do?bbsNo=19",
            date(2009, 5, 20),
            "포천시 도시관리계획 결정 공고",
            "https://www.pocheon.go.kr/www/selectBbsNttView.do?bbsNo=19&nttNo=1901",
        ),
        (
            "cheorwon_rss.xml",
            "철원군",
            "https://www.cwg.go.kr/rssBbsNtt.do?bbsNo=25",
            date(2026, 2, 11),
            "철원군 제안서 평가위원(후보자) 모집 공고",
            "https://www.cwg.go.kr/www/selectBbsNttView.do?bbsNo=25&nttNo=2501",
        ),
        (
            "jecheon_rss.xml",
            "제천시",
            "https://www.jecheon.go.kr/rssBbsNtt.do?bbsNo=18",
            date(2026, 2, 13),
            "특정공법 제안서 평가 결과 공개",
            "http://www.jecheon.go.kr/www/selectBbsNttView.do?bbsNo=18&nttNo=1801",
        ),
        (
            "okcheon_rss.xml",
            "옥천군",
            "https://www.oc.go.kr/rssBbsNtt.do?bbsNo=40",
            date(2026, 2, 19),
            "2026년도 옥천군 성별영향평가위원회 모집",
            "https://www.oc.go.kr/www/selectBbsNttView.do?bbsNo=40&nttNo=4001",
        ),
    ],
)
def test_parse_municipal_rss_notices_filters_by_date_and_keyword(
    fixture_name: str,
    municipality: str,
    list_url: str,
    target_date: date,
    expected_title: str,
    expected_url: str,
) -> None:
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / fixture_name
    rss_xml = fixture_path.read_text(encoding="utf-8")
    fetched_at = datetime(2026, 2, 22, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))

    notices = parse_municipal_rss_notices(
        rss_xml,
        municipality=municipality,
        list_url=list_url,
        target_date=target_date,
        fetched_at=fetched_at,
        source_type=SourceType.API,
    )

    assert len(notices) == 1
    assert notices[0].municipality == municipality
    assert notices[0].title == expected_title
    assert notices[0].published_date == target_date
    assert notices[0].url == expected_url


def test_parse_municipal_rss_notices_returns_empty_for_invalid_xml() -> None:
    fetched_at = datetime(2026, 2, 22, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))

    notices = parse_municipal_rss_notices(
        "<rss><channel><item></rss>",
        municipality="테스트시",
        list_url="https://example.com/rss",
        target_date=date(2026, 2, 22),
        fetched_at=fetched_at,
        source_type=SourceType.API,
    )

    assert notices == []


def test_parse_municipal_rss_notices_rewrites_ip_host_links_to_list_host() -> None:
    rss_xml = """
<rss version="2.0">
  <channel>
    <item>
      <title>제안서 평가위원 모집 공고</title>
      <link>https://27.101.144.78:443/www/selectBbsNttView.do?bbsNo=40&amp;nttNo=9001</link>
      <pubDate>2026-02-19</pubDate>
      <description>평가위원 안내</description>
    </item>
  </channel>
</rss>
"""
    fetched_at = datetime(2026, 2, 22, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))

    notices = parse_municipal_rss_notices(
        rss_xml,
        municipality="옥천군",
        list_url="https://www.oc.go.kr/rssBbsNtt.do?bbsNo=40",
        target_date=date(2026, 2, 19),
        fetched_at=fetched_at,
        source_type=SourceType.API,
    )

    assert len(notices) == 1
    assert notices[0].url == "https://www.oc.go.kr/www/selectBbsNttView.do?bbsNo=40&nttNo=9001"
