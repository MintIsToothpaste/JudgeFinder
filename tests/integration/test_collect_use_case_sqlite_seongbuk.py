from __future__ import annotations

from datetime import date
from pathlib import Path

from judgefinder.bootstrap import create_app
from judgefinder.domain.entities import SourceType


def test_collect_use_case_saves_seongbuk_notices_and_deduplicates(tmp_path: Path) -> None:
    db_path = tmp_path / "judgefinder.db"
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "seongbuk_rss.xml"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                'timezone = "Asia/Seoul"',
                f'db_path = "{db_path.as_posix()}"',
                'enabled_sources = ["seongbuk"]',
                "",
                "[sources.seongbuk]",
                'municipality = "성북구"',
                'source_type = "api"',
                'list_url = "https://www.sb.go.kr/www/gosiToRss.do"',
                f'fixture_path = "{fixture_path.as_posix()}"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    container = create_app(config_path=config_path)
    target_date = date(2026, 2, 16)

    collected = container.collect_use_case.execute(target_date)
    assert len(collected) == 2
    assert [notice.url for notice in collected] == [
        "https://www.sb.go.kr/www/notice/1001",
        "https://www.sb.go.kr/www/notice/1002",
    ]
    assert all(notice.source_type == SourceType.API for notice in collected)

    container.collect_use_case.execute(target_date)
    saved = container.list_use_case.execute(target_date)

    assert len(saved) == 2
    assert [notice.url for notice in saved] == [
        "https://www.sb.go.kr/www/notice/1001",
        "https://www.sb.go.kr/www/notice/1002",
    ]
