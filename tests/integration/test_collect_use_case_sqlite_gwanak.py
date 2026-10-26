from __future__ import annotations

import logging
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from click.testing import CliRunner

from judgefinder.adapters.config import load_config
from judgefinder.infrastructure.http.client import RequestsHttpClient
from judgefinder.interfaces.cli.main import app

ROOT = Path(__file__).parents[2]
GOSI_DETAIL = (
    "https://www.gwanak.go.kr/site/gwanak/ex/bbsNew/View.do?not_ancmt_mgt_no=41700&typeCode=1"
)
NEWS_DETAIL = (
    "https://www.gwanak.go.kr/site/gwanak/ex/bbs/View.do"
    "?cbIdx=239&bcIdx=204488&parentSeq=204488"
)
EMPTY_PAGE = (
    '<div id="boardDivId"><table class="list"><thead><tr><th>제목</th></tr></thead>'
    '<tbody><tr><td colspan="8">등록된 게시물이 없습니다.</td></tr></tbody></table></div>'
)


@pytest.mark.parametrize(("board", "filtered", "expected"), [
    ("gosi", True, [GOSI_DETAIL]), ("news", True, []), ("news", False, [NEWS_DETAIL]),
])
def test_gwanak_cli_collection_and_deduplication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    board: str, filtered: bool, expected: list[str],
) -> None:
    settings = load_config(ROOT / "config/config.example.toml").sources["gwanak"]
    assert settings.recruitment_only is True
    list_url = settings.list_url if board == "gosi" else (
        "https://www.gwanak.go.kr/site/gwanak/ex/bbs/List.do?cbIdx=239&pageIndex=1"
    )
    db_path = tmp_path / "notices.db"
    config = tmp_path / "config.toml"
    config.write_text(
        'timezone = "Asia/Seoul"\n'
        f'db_path = "{db_path.as_posix()}"\nenabled_sources = ["gwanak"]\n'
        '[sources.gwanak]\nmunicipality = "관악구"\nsource_type = "html"\n'
        f'engine_type = "generic_egov_bbs"\nlist_url = "{list_url}"\n'
        f'recruitment_only = {str(filtered).lower()}\n', encoding="utf-8",
    )
    payload = (ROOT / f"tests/fixtures/gwanak_{board}_list.html").read_text(encoding="utf-8")
    calls: list[str] = []

    def get_text(
        self: RequestsHttpClient, url: str, timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None, use_session: bool = False,
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
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
        f'fixture_path = "{fixture.as_posix()}"\n', encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING):
        result = CliRunner().invoke(app, [
            "--config-path", str(config), "collect", "--date", "2026-08-31",
        ])
    assert result.exit_code == 0
    assert "Skipping source 'gwanak'" in caplog.text
    assert "listing_rows=2, parsed=0" in caplog.text
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM notices").fetchone()[0] == 0
