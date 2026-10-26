from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from click.testing import CliRunner

from judgefinder.adapters.config import load_config
from judgefinder.infrastructure.http.client import RequestsHttpClient
from judgefinder.interfaces.cli.main import app


def test_hanam_html_cli_collect_list_and_deduplication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).parents[2]
    source = load_config(root / "config/config.example.toml").sources["hanam"]
    db_path = tmp_path / "notices.db"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join([
            'timezone = "Asia/Seoul"',
            f'db_path = "{db_path.as_posix()}"',
            'enabled_sources = ["hanam"]',
            '[sources.hanam]',
            f'municipality = "{source.municipality}"',
            f'source_type = "{source.source_type.value}"',
            f'engine_type = "{source.engine_type.value}"',
            f'list_url = "{source.list_url}"',
        ]),
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
        result = runner.invoke(app, [
            "--config-path", str(config_path), "collect", "--date", "2026-09-26", "--days", "14",
        ])
        assert result.exit_code == 0, result.output
        assert result.output.splitlines() == [expected_url]
    assert len(calls) == 4

    result = runner.invoke(app, [
        "--config-path", str(config_path), "list", "--date", "2026-09-26", "--days", "14",
    ])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [expected_url]
    assert len(calls) == 4
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT municipality, title, url, published_date, source_type FROM notices"
        ).fetchall()
    assert rows == [(
        "하남시",
        "「하남 교산지구 자족용지 핵심 타깃기업 발굴 용역」 제안서 평가위원(후보자) 모집 공고",
        expected_url,
        "2026-09-22",
        "html",
    )]
