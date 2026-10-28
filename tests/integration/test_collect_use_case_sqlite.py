from __future__ import annotations

import logging
import sqlite3
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from click.testing import CliRunner

from judgefinder.adapters.config import load_config
from judgefinder.bootstrap import create_app
from judgefinder.domain.entities import SourceType
from judgefinder.infrastructure.http.client import RequestsHttpClient
from judgefinder.interfaces.cli.main import app


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


ROOT = Path(__file__).parents[2]


GOSI_DETAIL = (
    "https://www.gwanak.go.kr/site/gwanak/ex/bbsNew/View.do?not_ancmt_mgt_no=41700&typeCode=1"
)


NEWS_DETAIL = (
    "https://www.gwanak.go.kr/site/gwanak/ex/bbs/View.do?cbIdx=239&bcIdx=204488&parentSeq=204488"
)


EMPTY_PAGE = (
    '<div id="boardDivId"><table class="list"><thead><tr><th>제목</th></tr></thead>'
    '<tbody><tr><td colspan="8">등록된 게시물이 없습니다.</td></tr></tbody></table></div>'
)


@pytest.mark.parametrize(
    ("board", "filtered", "expected"),
    [
        ("gosi", True, [GOSI_DETAIL]),
        ("news", True, []),
        ("news", False, [NEWS_DETAIL]),
    ],
)
def test_gwanak_cli_collection_and_deduplication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    board: str,
    filtered: bool,
    expected: list[str],
) -> None:
    settings = load_config(ROOT / "config/config.example.toml").sources["gwanak"]
    assert settings.recruitment_only is True
    list_url = (
        settings.list_url
        if board == "gosi"
        else ("https://www.gwanak.go.kr/site/gwanak/ex/bbs/List.do?cbIdx=239&pageIndex=1")
    )
    db_path = tmp_path / "notices.db"
    config = tmp_path / "config.toml"
    config.write_text(
        'timezone = "Asia/Seoul"\n'
        f'db_path = "{db_path.as_posix()}"\nenabled_sources = ["gwanak"]\n'
        '[sources.gwanak]\nmunicipality = "관악구"\nsource_type = "html"\n'
        f'engine_type = "generic_egov_bbs"\nlist_url = "{list_url}"\n'
        f"recruitment_only = {str(filtered).lower()}\n",
        encoding="utf-8",
    )
    payload = (ROOT / f"tests/fixtures/gwanak_{board}_list.html").read_text(encoding="utf-8")
    calls: list[str] = []

    def get_text(
        self: RequestsHttpClient,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        calls.append(url)
        query = parse_qs(urlparse(url).query)
        assert query["searchKey"] == ["평가위원"]
        assert query["tgtTypeCd"] == ["NOT_ANCMT_SJ" if board == "gosi" else "SUB_CONT"]
        assert "searchKrwd" not in query
        assert verify_tls is True
        return payload if query["pageIndex"] == ["1"] else EMPTY_PAGE

    monkeypatch.setattr(RequestsHttpClient, "get_text", get_text)
    runner = CliRunner()
    base = ["--config-path", str(config)]
    for _ in range(2):
        result = runner.invoke(app, [*base, "collect", "--date", "2026-08-31"])
        assert result.exit_code == 0, result.output
        assert result.stdout.splitlines() == expected
    assert len(calls) == 4
    result = runner.invoke(app, [*base, "list", "--date", "2026-08-31"])
    assert result.exit_code == 0
    assert result.stdout.splitlines() == expected
    assert len(calls) == 4
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT municipality, url, published_date, source_type FROM notices"
        ).fetchall()
    assert rows == [("관악구", url, "2026-08-31", "html") for url in expected]

    result = runner.invoke(app, [*base, "collect", "--date", "2026-09-01"])
    assert result.exit_code == 0
    assert result.stdout == ""


def test_parse_failure_reaches_cli_warning_without_saving(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    html = (ROOT / "tests/fixtures/gwanak_gosi_list.html").read_text(encoding="utf-8")
    fixture = tmp_path / "broken.html"
    fixture.write_text(html.replace("doBbsFView", "unsupportedView"), encoding="utf-8")
    db_path = tmp_path / "notices.db"
    config = tmp_path / "config.toml"
    config.write_text(
        'timezone = "Asia/Seoul"\n'
        f'db_path = "{db_path.as_posix()}"\nenabled_sources = ["gwanak"]\n'
        '[sources.gwanak]\nmunicipality = "관악구"\nsource_type = "html"\n'
        'engine_type = "generic_egov_bbs"\n'
        'list_url = "https://www.gwanak.go.kr/site/gwanak/ex/bbsNew/List.do?typeCode=1"\n'
        f'fixture_path = "{fixture.as_posix()}"\n',
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING):
        result = CliRunner().invoke(
            app,
            [
                "--config-path",
                str(config),
                "collect",
                "--date",
                "2026-08-31",
            ],
        )
    assert result.exit_code == 0
    assert "Skipping source 'gwanak'" in caplog.text
    assert "listing_rows=2, parsed=0" in caplog.text
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM notices").fetchone()[0] == 0


def test_hanam_html_cli_collect_list_and_deduplication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).parents[2]
    source = load_config(root / "config/config.example.toml").sources["hanam"]
    db_path = tmp_path / "notices.db"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                'timezone = "Asia/Seoul"',
                f'db_path = "{db_path.as_posix()}"',
                'enabled_sources = ["hanam"]',
                "[sources.hanam]",
                f'municipality = "{source.municipality}"',
                f'source_type = "{source.source_type.value}"',
                f'engine_type = "{source.engine_type.value}"',
                f'list_url = "{source.list_url}"',
            ]
        ),
        encoding="utf-8",
    )
    payload = (root / "tests/fixtures/hanam_gosi_list.html").read_text(encoding="utf-8")
    calls: list[str] = []

    def get_text(
        self: RequestsHttpClient,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        calls.append(url)
        query = parse_qs(urlparse(url).query)
        assert urlparse(url).path == "/www/selectGosiList.do"
        assert query["searchCnd"] == ["SJ"]
        assert query["searchKrwd"] == ["평가위원"]
        assert query["not_ancmt_se_code"] == ["01,04"]
        assert verify_tls is True
        return payload if query["pageIndex"] == ["1"] else "<html></html>"

    monkeypatch.setattr(RequestsHttpClient, "get_text", get_text)
    runner = CliRunner()
    expected_url = (
        "https://www.hanam.go.kr/www/selectGosiData.do"
        "?key=171&not_ancmt_mgt_no=52650&not_ancmt_se_code=01,04"
    )
    for _ in range(2):
        result = runner.invoke(
            app,
            [
                "--config-path",
                str(config_path),
                "collect",
                "--date",
                "2026-09-26",
                "--days",
                "14",
            ],
        )
        assert result.exit_code == 0, result.output
        assert result.output.splitlines() == [expected_url]
    assert len(calls) == 4

    result = runner.invoke(
        app,
        [
            "--config-path",
            str(config_path),
            "list",
            "--date",
            "2026-09-26",
            "--days",
            "14",
        ],
    )
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [expected_url]
    assert len(calls) == 4
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT municipality, title, url, published_date, source_type FROM notices"
        ).fetchall()
    assert rows == [
        (
            "하남시",
            "「하남 교산지구 자족용지 핵심 타깃기업 발굴 용역」 제안서 평가위원(후보자) 모집 공고",
            expected_url,
            "2026-09-22",
            "html",
        )
    ]


@pytest.mark.parametrize(
    ("slug", "municipality", "list_url", "fixture_name", "target_date", "expected_url"),
    [
        (
            "pocheon",
            "포천시",
            "https://www.pocheon.go.kr/www/selectEminwonList.do?key=12563&notAncmtSeCode=01",
            "pocheon_eminwon_list.html",
            date(2026, 2, 2),
            "https://www.pocheon.go.kr/www/selectEminwonView.do?key=12563&notAncmtMgtNo=64616&notAncmtSeCode=01",
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
