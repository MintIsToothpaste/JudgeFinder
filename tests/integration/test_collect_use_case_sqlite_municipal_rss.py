from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from judgefinder.bootstrap import create_app
from judgefinder.domain.entities import SourceType


@pytest.mark.parametrize(
    ("slug", "municipality", "list_url", "fixture_name", "target_date", "expected_url"),
    [
        (
            "hanam",
            "하남시",
            "https://www.hanam.go.kr/rssBbsNtt.do?bbsNo=31",
            "hanam_rss.xml",
            date(2015, 8, 27),
            "https://www.hanam.go.kr/www/selectBbsNttView.do?bbsNo=31&nttNo=3101",
        ),
        (
            "pocheon",
            "포천시",
            "https://www.pocheon.go.kr/rssBbsNtt.do?bbsNo=19",
            "pocheon_rss.xml",
            date(2009, 5, 20),
            "https://www.pocheon.go.kr/www/selectBbsNttView.do?bbsNo=19&nttNo=1901",
        ),
        (
            "cheorwon",
            "철원군",
            "https://www.cwg.go.kr/rssBbsNtt.do?bbsNo=25",
            "cheorwon_rss.xml",
            date(2026, 2, 11),
            "https://www.cwg.go.kr/www/selectBbsNttView.do?bbsNo=25&nttNo=2501",
        ),
        (
            "jecheon",
            "제천시",
            "https://www.jecheon.go.kr/rssBbsNtt.do?bbsNo=18",
            "jecheon_rss.xml",
            date(2026, 2, 13),
            "http://www.jecheon.go.kr/www/selectBbsNttView.do?bbsNo=18&nttNo=1801",
        ),
        (
            "okcheon",
            "옥천군",
            "https://www.oc.go.kr/rssBbsNtt.do?bbsNo=40",
            "okcheon_rss.xml",
            date(2026, 2, 19),
            "https://www.oc.go.kr/www/selectBbsNttView.do?bbsNo=40&nttNo=4001",
        ),
    ],
)
def test_collect_use_case_saves_municipal_rss_notices_and_deduplicates(
    tmp_path: Path,
    slug: str,
    municipality: str,
    list_url: str,
    fixture_name: str,
    target_date: date,
    expected_url: str,
) -> None:
    db_path = tmp_path / "judgefinder.db"
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / fixture_name
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                'timezone = "Asia/Seoul"',
                f'db_path = "{db_path.as_posix()}"',
                f'enabled_sources = ["{slug}"]',
                "",
                f"[sources.{slug}]",
                f'municipality = "{municipality}"',
                'source_type = "api"',
                f'list_url = "{list_url}"',
                f'fixture_path = "{fixture_path.as_posix()}"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    container = create_app(config_path=config_path)

    collected = container.collect_use_case.execute(target_date)
    assert len(collected) == 1
    assert collected[0].url == expected_url
    assert collected[0].source_type == SourceType.API

    container.collect_use_case.execute(target_date)
    saved = container.list_use_case.execute(target_date)

    assert len(saved) == 1
    assert saved[0].url == expected_url
