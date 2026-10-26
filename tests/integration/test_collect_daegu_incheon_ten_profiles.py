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


def test_ten_sources_recruitment_filter_pagination_deduplication_and_offline_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads((ROOT / "tests/fixtures/daegu_incheon_ten_profiles.json").read_text())
    example = ROOT / "config/batch-daegu-incheon-ten.example.toml"
    settings = load_config(example)
    db, config = tmp_path / "notices.db", tmp_path / "config.toml"
    config.write_text(
        example.read_text().replace(
            "data/live-tests/daegu-incheon-ten-2026-10-04/notices.db", db.as_posix(),
        )
        .replace("throttle_seconds = 1.0", "throttle_seconds = 0.0"), encoding="utf-8",
    )
    assert load_config(config).db_path == db
    sources = {urlparse(s.list_url).netloc: s for s in settings.sources.values()}
    calls: list[tuple[str, str, int]] = []

    def get_text(
        self: RequestsHttpClient, url: str, timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None, use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        assert verify_tls and use_session and headers is not None and "Referer" in headers
        source = sources[urlparse(url).netloc]
        case, profile = cases[source.slug], source.html_profile
        assert profile is not None
        if url == case["url"] and case["detail_html"]:
            calls.append((source.slug, "detail", 0))
            return str(case["detail_html"])
        query = parse_qs(urlparse(url).query, keep_blank_values=True)
        if profile.search_param:
            if source.slug == "incheon":
                assert "conTitle=%C6%F2%B0%A1%C0%A7%BF%F8" in url
                assert query["conGosiGbn"] == ["A"]
            else:
                assert query[profile.search_param] == ["평가위원"]
        else:
            assert not any(k in query for k in ("keyword", "srchVal", "srchValue"))
        page = int(query[profile.page_param][0])
        assert page in (1, 2), "repeated final page must stop pagination"
        calls.append((source.slug, "list", page))
        return str(case["list_html"])

    monkeypatch.setattr(RequestsHttpClient, "get_text", get_text)
    runner, args = CliRunner(), ["--config-path", str(config)]
    window = ["--date", "2026-10-04", "--days", "365"]
    outputs = []
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            result = runner.invoke(app, [*args, "collect", *window])
            assert result.exit_code == 0, result.output
            outputs.append(result.stdout)
    assert "Skipping source" not in caplog.text
    positive = {slug: c for slug, c in cases.items() if c["category"] == "recruitment"}
    assert len(positive) == 7 and outputs[0] == outputs[1]
    assert len(outputs[0].splitlines()) == 7
    with sqlite3.connect(db) as conn:
        actual = conn.execute(
            "select municipality,title,published_date,url from notices order by municipality",
        ).fetchall()
    assert actual == sorted(
        (settings.sources[slug].municipality, c["title"], c["date"], c["url"])
        for slug, c in positive.items()
    )
    before = len(calls)
    listed = runner.invoke(app, [*args, "list", *window])
    assert listed.exit_code == 0 and listed.stdout == outputs[0] and len(calls) == before
    for slug, case in cases.items():
        assert sum(s == slug and kind == "detail" for s, kind, _ in calls) == (
            2 if case["detail_html"] else 0
        )
        assert sum(s == slug and kind == "list" for s, kind, _ in calls) == 4
