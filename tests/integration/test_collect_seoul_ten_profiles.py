from __future__ import annotations

import json
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


def test_ten_sources_cli_dates_detail_enrichment_and_sqlite_dedup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads(
        (ROOT / "tests/fixtures/seoul_ten_profiles.json").read_text(encoding="utf-8"),
    )
    example = ROOT / "config/batch-seoul-ten.example.toml"
    settings = load_config(example)
    db = tmp_path / "notices.db"
    config = tmp_path / "config.toml"
    config.write_text(
        example.read_text(encoding="utf-8")
        .replace("data/live-tests/seoul-ten-2026-09-27/notices.db", db.as_posix())
        .replace("throttle_seconds = 1.0", "throttle_seconds = 0.0"), encoding="utf-8",
    )
    by_host = {urlparse(s.list_url).netloc: s for s in settings.sources.values()}
    calls: list[tuple[str, str, int]] = []

    def listing(slug: str, page: int) -> str:
        case = cases[slug]
        soup = BeautifulSoup(case["list_html"], "html.parser")
        if page > 1:
            profile = settings.sources[slug].html_profile
            assert profile is not None
            container = soup.select_one(profile.container_selector)
            assert container is not None
            container.clear()
        return str(soup)

    def get_text(
        self: RequestsHttpClient, url: str, timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None, use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        source = by_host[urlparse(url).netloc]
        case = cases[source.slug]
        assert verify_tls
        if url == case["url"]:
            calls.append((source.slug, "detail", 0))
            assert case["detail_html"]
            return str(case["detail_html"])
        profile = source.html_profile
        assert profile is not None and profile.request_method == "GET"
        params = parse_qs(urlparse(url).query)
        assert params[profile.search_param] == ["평가위원"]
        page = int(params[profile.page_param][0])
        calls.append((source.slug, "GET", page))
        return listing(source.slug, page)

    def post_text(
        self: RequestsHttpClient, url: str, *, data: bytes, timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None, use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        assert verify_tls
        source = by_host[urlparse(url).netloc]
        if source.slug == "seodaemun":
            params = parse_qs(data.decode("ascii"), encoding="euc-kr")
            assert params["keyword"] == ["평가위원"]
            page = int(params["cp"][0])
            calls.append((source.slug, "POST", page))
            return listing(source.slug, page)
        assert source.slug == "mapo"
        params = parse_qs(data.decode("ascii"))
        query = json.loads(params["objData"][0].splitlines()[1])
        page = query["from"] // 10 + 1
        calls.append((source.slug, "POST", page))
        case = cases["mapo"]
        hits = [{"_source": {
            "ba_title": case["title"], "ba_regdate": case["date"],
            "link_url": urlparse(case["url"]).path + "?cp=1",
        }}] if page == 1 else []
        return json.dumps({"responses": [{"hits": {"hits": hits}}]})

    monkeypatch.setattr(RequestsHttpClient, "get_text", get_text)
    monkeypatch.setattr(RequestsHttpClient, "post_text", post_text)
    runner = CliRunner()
    base = ["--config-path", str(config)]
    outputs = []
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            result = runner.invoke(app, [*base, "collect", "--date", "2026-09-27", "--days", "365"])
            assert result.exit_code == 0, result.output
            outputs.append(result.stdout)
    assert "Skipping source" not in caplog.text
    assert outputs[0] == outputs[1]
    assert len(outputs[0].splitlines()) == 10
    with sqlite3.connect(db) as conn:
        actual = conn.execute(
            "SELECT municipality, title, published_date, url FROM notices ORDER BY municipality",
        ).fetchall()
    expected = sorted([
        (settings.sources[slug].municipality, case["title"], case["date"], case["url"])
        for slug, case in cases.items()
    ])
    assert actual == expected
    for slug in settings.sources:
        assert sum(s == slug and kind != "detail" for s, kind, _ in calls) == 4
        assert sum(s == slug and kind == "detail" for s, kind, _ in calls) == (
            2 if cases[slug]["detail_html"] else 0
        )
    before = len(calls)
    result = runner.invoke(app, [*base, "list", "--date", "2026-09-27", "--days", "365"])
    assert result.exit_code == 0
    assert result.stdout == outputs[0]
    assert len(calls) == before
