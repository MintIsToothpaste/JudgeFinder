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


def test_recovered_profiles_cli_pagination_dedup_and_offline_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads((ROOT / "tests/fixtures/held_eighteen_recovered_profiles.json").read_text())
    example = ROOT / "config/batch-held-eighteen.example.toml"
    settings = load_config(example)
    config, db = tmp_path / "config.toml", tmp_path / "notices.db"
    config.write_text(example.read_text().replace(
        "data/live-tests/held-eighteen-2026-10-05/notices.db", db.as_posix(),
    ).replace("throttle_seconds = 0.3", "throttle_seconds = 0.0"))
    details = {c["url"]: c["detail_html"] for c in cases.values()}
    calls: list[str] = []
    seen: set[str] = set()

    def get_text(
        self: RequestsHttpClient, url: str, timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None, use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        assert verify_tls and use_session and headers and "Referer" in headers
        calls.append(url)
        if url in details:
            return str(details[url])
        parsed, query = urlparse(url), parse_qs(urlparse(url).query, keep_blank_values=True)
        source = next(s for s in settings.sources.values()
            if urlparse(s.list_url).netloc == parsed.netloc)
        seen.add(source.slug)
        profile, case = source.html_profile, cases[source.slug]
        assert query[profile.search_param] == ["평가위원"]
        page = int(query[profile.page_param][0])
        assert page in (1, 2)
        if page == 1:
            return str(case["list_html"])
        soup = BeautifulSoup(case["list_html"], "html5lib")
        container = soup.select_one(profile.container_selector)
        for row in container.select(profile.row_selector):
            row.decompose()
        soup.select_one(profile.page_number_selector).string = "2"
        return str(soup)

    monkeypatch.setattr(RequestsHttpClient, "get_text", get_text)
    runner, args = CliRunner(), ["--config-path", str(config)]
    window = ["--date", "2026-10-05", "--days", "365"]
    outputs = []
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            result = runner.invoke(app, [*args, "collect", *window])
            assert result.exit_code == 0, result.output
            outputs.append(result.stdout)
    assert "Skipping source" not in caplog.text and outputs[0] == outputs[1]
    assert seen == set(settings.enabled_sources)
    with sqlite3.connect(db) as connection:
        actual = connection.execute(
            "select municipality,title,published_date,url from notices",
        ).fetchall()
    expected = [(settings.sources[slug].municipality, c["title"], c["date"], c["url"])
        for slug, c in cases.items()]
    assert sorted(actual) == sorted(expected)
    count = len(calls)
    listed = runner.invoke(app, [*args, "list", *window])
    assert listed.exit_code == 0 and listed.stdout == outputs[0] and len(calls) == count
