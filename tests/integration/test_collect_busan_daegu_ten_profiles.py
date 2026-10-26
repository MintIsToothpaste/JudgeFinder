from __future__ import annotations

import json
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


def test_ten_sources_public_links_pagination_dedup_and_offline_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads((ROOT / "tests/fixtures/busan_daegu_ten_profiles.json").read_text())
    example = ROOT / "config/batch-busan-daegu-ten.example.toml"
    settings = load_config(example)
    db = tmp_path / "notices.db"
    config = tmp_path / "config.toml"
    config.write_text(
        example.read_text().replace(
            "data/live-tests/busan-daegu-ten-2026-10-03/notices.db", db.as_posix(),
        ).replace("throttle_seconds = 1.0", "throttle_seconds = 0.0"), encoding="utf-8",
    )
    sources = {urlparse(s.list_url).netloc: s for s in settings.sources.values()}
    calls: list[tuple[str, str, int]] = []

    def get_text(
        self: RequestsHttpClient, url: str, timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None, use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        assert verify_tls and use_session and headers is not None and "Referer" in headers
        source = sources[urlparse(url).netloc]
        case = cases[source.slug]
        if url == case["url"]:
            calls.append((source.slug, "detail", 0))
            return str(case["detail_html"])
        profile = source.html_profile
        assert profile is not None and profile.request_method == "GET"
        query = parse_qs(urlparse(url).query, keep_blank_values=True)
        assert query[profile.search_param] == ["평가위원"]
        assert "yyyy" not in query and "recent_mm" not in query
        if source.slug == "daegu_seogu":
            assert query["endYn"] == [""]
        if source.slug == "daegu":
            assert query["searchGosi_gbn"] == ["A"]
        page = int(query[profile.page_param][0])
        assert page in (1, 2), "repeated last page must stop pagination"
        calls.append((source.slug, "list", page))
        return str(case["list_html"])

    monkeypatch.setattr(RequestsHttpClient, "get_text", get_text)
    runner = CliRunner()
    args = ["--config-path", str(config)]
    window = ["--date", "2026-10-03", "--days", "365"]
    outputs = []
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            result = runner.invoke(app, [*args, "collect", *window])
            assert result.exit_code == 0, result.output
            outputs.append(result.stdout)
    assert "Skipping source" not in caplog.text
    assert outputs[0] == outputs[1] and len(outputs[0].splitlines()) == 10
    with sqlite3.connect(db) as conn:
        actual = conn.execute(
            "SELECT municipality,title,published_date,url FROM notices ORDER BY municipality",
        ).fetchall()
    assert actual == sorted(
        (settings.sources[slug].municipality, case["title"], case["date"], case["url"])
        for slug, case in cases.items()
    )
    for slug in cases:
        assert sum(s == slug and kind == "detail" for s, kind, _ in calls) == 2
        assert sum(s == slug and kind == "list" for s, kind, _ in calls) == 4
    before = len(calls)
    listed = runner.invoke(app, [*args, "list", *window])
    assert listed.exit_code == 0 and listed.stdout == outputs[0]
    assert len(calls) == before
