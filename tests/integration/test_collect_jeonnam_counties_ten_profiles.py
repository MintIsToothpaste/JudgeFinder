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


def test_real_profiles_collection_pagination_deduplication_and_offline_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads((ROOT / "tests/fixtures/jeonnam_counties_ten_profiles.json").read_text())
    nomination = json.loads((ROOT / "tests/fixtures/gangjin_nomination_profile.json").read_text())
    example = ROOT / "config/batch-jeonnam-counties-ten.example.toml"
    settings = load_config(example)
    config, db = tmp_path / "config.toml", tmp_path / "notices.db"
    config.write_text(example.read_text().replace(
        "data/live-tests/jeonnam-counties-ten-2026-10-04/notices.db", db.as_posix(),
    ).replace("throttle_seconds = 1.0", "throttle_seconds = 0.0"), encoding="utf-8")
    assert load_config(config).db_path == db
    details = {case["url"]: case for case in cases.values() if "detail_html" in case}
    details[nomination["gangjin"]["url"]] = nomination["gangjin"]
    calls: list[str] = []
    seen: set[str] = set()

    def get_text(
        self: RequestsHttpClient, url: str, timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None, use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        assert verify_tls and use_session and headers is not None and "Referer" in headers
        calls.append(url)
        if url in details:
            return str(details[url]["detail_html"])
        parsed, query = urlparse(url), parse_qs(urlparse(url).query)

        def matches(list_url: str) -> bool:
            base, required = urlparse(list_url), parse_qs(urlparse(list_url).query)
            return ((base.netloc, base.path) == (parsed.netloc, parsed.path)
                and all(query.get(k) == v for k, v in required.items())
                and query.get("category_1", [""]) == required.get("category_1", [""]))

        source = next(s for s in settings.sources.values() if matches(s.list_url))
        seen.add(source.slug)
        profile, case = source.html_profile, cases[source.slug]
        assert profile is not None
        assert query[profile.search_param] == ["평가위원"]
        page = int(query[profile.page_param][0])
        assert page in (1, 2)
        # An explicit empty second page exercises pagination, not repeated page-one data.
        if page == 2:
            if source.slug == "gurye":
                return '<table class="board_list"><tbody></tbody></table>' \
                    '<li class="current"><a>2</a></li>'
            if source.slug == "haenam":
                return '<table class="board_list"><tbody></tbody></table>' \
                    '<div class="pagination"><a class="select">2</a></div>'
            soup = BeautifulSoup(case.get("list_html", case.get("empty_list_html")), "html5lib")
            container = soup.select_one(profile.container_selector)
            assert container is not None
            container.clear()
            return str(container)
        payload = str(case.get("list_html", case.get("empty_list_html")))
        if source.slug == "gangjin":
            soup = BeautifulSoup(payload, "html5lib")
            additional = BeautifulSoup(nomination["gangjin"]["list_html"], "html5lib")
            row = additional.select_one(profile.row_selector)
            body = soup.select_one("tbody")
            assert row is not None and body is not None
            body.append(row)
            return str(soup)
        return payload

    monkeypatch.setattr(RequestsHttpClient, "get_text", get_text)
    runner, args = CliRunner(), ["--config-path", str(config)]
    window = ["--date", "2026-10-04", "--days", "365"]
    outputs = []
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            result = runner.invoke(app, [*args, "collect", *window])
            assert result.exit_code == 0, result.output
            outputs.append(result.stdout)
    assert "Skipping source" not in caplog.text and outputs[0] == outputs[1]
    assert seen == set(settings.enabled_sources)
    positive = {slug: c for slug, c in cases.items() if c.get("category") == "recruitment"}
    assert len(positive) == 10 and len(outputs[0].splitlines()) == 11
    with sqlite3.connect(db) as conn:
        actual = conn.execute(
            "select municipality,title,published_date,url from notices order by municipality",
        ).fetchall()
    expected = [(settings.sources[slug].municipality, c["title"], c["date"], c["url"])
        for slug, c in positive.items()]
    c = nomination["gangjin"]
    expected.append((settings.sources["gangjin"].municipality, c["title"], c["date"], c["url"]))
    assert sorted(actual) == sorted(expected)
    count = len(calls)
    listed = runner.invoke(app, [*args, "list", *window])
    assert listed.exit_code == 0 and listed.stdout == outputs[0] and len(calls) == count
