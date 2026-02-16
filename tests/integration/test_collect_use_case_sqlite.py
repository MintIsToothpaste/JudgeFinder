from __future__ import annotations

from datetime import date
from pathlib import Path

from judgefinder.bootstrap import create_app


def test_collect_use_case_saves_into_sqlite_and_deduplicates(tmp_path: Path) -> None:
    db_path = tmp_path / "judgefinder.db"
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "sample_city_list.html"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                'timezone = "Asia/Seoul"',
                f'db_path = "{db_path.as_posix()}"',
                'enabled_sources = ["sample_city"]',
                "",
                "[sources.sample_city]",
                'municipality = "샘플시"',
                'source_type = "html"',
                'list_url = "https://example.com/sample_city/notices"',
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

    container.collect_use_case.execute(target_date)
    saved = container.list_use_case.execute(target_date)

    assert len(saved) == 2
    assert [notice.url for notice in saved] == [
        "https://example.com/sample-city/notices/20260216-a",
        "https://example.com/sample-city/notices/20260216-b",
    ]
