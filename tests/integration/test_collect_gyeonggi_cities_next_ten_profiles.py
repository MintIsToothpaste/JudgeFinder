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


def test_real_profiles_pagination_exclusion_deduplication_and_offline_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads((ROOT / "tests/fixtures/gyeonggi_cities_next_ten_profiles.json").read_text())
    example = ROOT / "config/batch-gyeonggi-cities-next-ten.example.toml"
    settings = load_config(example)
    config, db = tmp_path / "config.toml", tmp_path / "notices.db"
    config.write_text(example.read_text().replace(
        "data/live-tests/gyeonggi-cities-next-ten-2026-10-04/notices.db", db.as_posix(),
    )
        .replace("throttle_seconds = 1.0", "throttle_seconds = 0.0"), encoding="utf-8")
    assert load_config(config).db_path == db
    details = {c["url"]: c["detail_html"] for c in cases.values() if "detail_html" in c}
    calls: list[str] = []
    seen: set[str] = set()

    def get_text(
        self: RequestsHttpClient, url: str, timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None, use_session: bool = False,
        verify_tls: bool = True, _post: bool = False,
    ) -> str:
        assert verify_tls and use_session and headers is not None and "Referer" in headers
        calls.append(url)
        if url in details:
            return str(details[url])
        parsed, query = urlparse(url), parse_qs(urlparse(url).query)

        def matches(list_url: str) -> bool:
            base, required = urlparse(list_url), parse_qs(urlparse(list_url).query)
            return ((base.netloc, base.path) == (parsed.netloc, parsed.path)
                and all(query.get(k) == v for k, v in required.items()))

        source = next(s for s in settings.sources.values() if matches(s.list_url))
        seen.add(source.slug)
        profile, case = source.html_profile, cases[source.slug]
        assert profile is not None
        assert (profile.request_method == "POST") == _post
        assert query[profile.search_param] == ["평가위원"]
        page = int(query[profile.page_param][0])
        assert page in (1, 2)
        if page == 1:
            return str(case["list_html"])
        soup = BeautifulSoup(case["list_html"], "html5lib")
        container = soup.select_one(profile.container_selector)
        assert container is not None
        for body in container.find_all("tbody", recursive=False):
            body.clear()
        if profile.page_number_selector:
            current = soup.select_one(profile.page_number_selector)
            assert current is not None
            current.string = "2"
        return str(soup)

    def post_text(
        self: RequestsHttpClient, url: str, data: bytes, timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None, use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        assert data.isascii()
        return get_text(self, url + "?" + data.decode("ascii"),
            timeout_seconds=timeout_seconds, headers=headers, use_session=use_session,
            verify_tls=verify_tls, _post=True)

    monkeypatch.setattr(RequestsHttpClient, "get_text", get_text)
    monkeypatch.setattr(RequestsHttpClient, "post_text", post_text)
    runner, args = CliRunner(), ["--config-path", str(config)]
    window = ["--date", "2026-10-04", "--days", "365"]
    outputs = []
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            result = runner.invoke(app, [*args, "collect", *window])
            assert result.exit_code == 0, result.output
            outputs.append(result.stdout)
    assert "Skipping source" not in caplog.text and outputs[0] == outputs[1]
    assert seen == set(settings.enabled_sources) and len(outputs[0].splitlines()) == 10
    with sqlite3.connect(db) as conn:
        actual = conn.execute(
            "select municipality,title,published_date,url from notices",
        ).fetchall()
    expected = [(settings.sources[slug].municipality, c["title"], c["date"], c["url"])
        for slug, c in cases.items() if c["category"] == "recruitment"]
    assert sorted(actual) == sorted(expected)
    count = len(calls)
    listed = runner.invoke(app, [*args, "list", *window])
    assert listed.exit_code == 0 and listed.stdout == outputs[0] and len(calls) == count
