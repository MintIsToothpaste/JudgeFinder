from __future__ import annotations

import logging
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from bs4 import BeautifulSoup
from click.testing import CliRunner

from judgefinder.adapters.config import load_config
from judgefinder.infrastructure.http.client import RequestsHttpClient
from judgefinder.interfaces.cli.main import app

ROOT = Path(__file__).parents[2]


def test_five_profiles_through_cli_with_pagination_and_sqlite_dedup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    example = ROOT / "config/batch-seoul-five.example.toml"
    settings = load_config(example)
    config = tmp_path / "config.toml"
    db = tmp_path / "notices.db"
    config.write_text(
        example.read_text(encoding="utf-8")
        .replace("data/live-tests/batch-2026-09-27/notices.db", db.as_posix())
        .replace("throttle_seconds = 1.0", "throttle_seconds = 0.0"), encoding="utf-8",
    )
    by_host = {urlparse(s.list_url).netloc: s for s in settings.sources.values()}
    calls: list[tuple[str, int]] = []

    def get_text(
        self: RequestsHttpClient, url: str, timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None, use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        parsed = urlparse(url)
        source = by_host[parsed.netloc]
        profile = source.html_profile
        assert profile is not None
        query = parse_qs(parsed.query)
        assert query[profile.search_param] == ["평가위원"]
        assert verify_tls is True
        page = int(query[profile.page_param][0])
        calls.append((source.slug, page))
        payload = (ROOT / f"tests/fixtures/{source.slug}_profile_list.html").read_text(
            encoding="utf-8",
        )
        if page > 1:
            soup = BeautifulSoup(payload, "html.parser")
            for tbody in soup.select("tbody"):
                tbody.clear()
            return str(soup)
        return payload

    monkeypatch.setattr(RequestsHttpClient, "get_text", get_text)
    runner = CliRunner()
    base = ["--config-path", str(config)]
    outputs: list[str] = []
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            result = runner.invoke(app, [*base, "collect", "--date", "2026-09-27", "--days", "180"])
            assert result.exit_code == 0, result.output
            outputs.append(result.stdout)
    assert "Skipping source" not in caplog.text
    assert outputs[0] == outputs[1]
    assert len(outputs[0].splitlines()) == 5
    assert set(calls) == {(slug, page) for slug in settings.sources for page in (1, 2)}
    assert len(calls) == 20  # Pages are fetched once per run, not once per target date.
    with sqlite3.connect(db) as conn:
        actual = conn.execute(
            "SELECT municipality, published_date, source_type FROM notices ORDER BY municipality"
        ).fetchall()
    assert actual == sorted([
        ("서울특별시", "2026-08-05", "html"),
        ("종로구", "2026-09-21", "html"),
        ("서울 중구", "2026-04-08", "html"),
        ("용산구", "2026-07-22", "html"),
        ("성동구", "2026-09-22", "html"),
    ])
    result = runner.invoke(app, [*base, "list", "--date", "2026-09-27", "--days", "180"])
    assert result.exit_code == 0
    assert result.stdout == outputs[0]
    assert len(calls) == 20
