from __future__ import annotations

import json
import logging
import re
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


def test_supplemental_boards_collect_store_deduplicate_and_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads(
        (ROOT / "tests/fixtures/cafe_20261023_profiles.json").read_text(encoding="utf-8"),
    )
    example = ROOT / "config/batch-cafe-20261023.example.toml"
    settings = load_config(example)
    config, db = tmp_path / "config.toml", tmp_path / "notices.db"
    text = re.sub(
        r"^db_path = .+$",
        "db_path = " + json.dumps(db.as_posix()),
        example.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    config.write_text(
        text.replace("throttle_seconds = 0.3", "throttle_seconds = 0.0"), encoding="utf-8"
    )
    by_host = {urlparse(source.list_url).netloc: slug for slug, source in settings.sources.items()}
    details = {case["url"]: case["detail_html"] for case in cases.values()}
    calls: list[str] = []
    seen: set[str] = set()

    def respond(url: str) -> str:
        calls.append(url)
        if url in details:
            return str(details[url])
        slug = by_host[urlparse(url).netloc]
        seen.add(slug)
        profile = settings.sources[slug].html_profile
        assert profile is not None
        query = parse_qs(urlparse(url).query)
        page = int(query.get(profile.page_param, ["1"])[0])
        assert page in {1, 2}
        if slug == "gyeongnam_education" and page == 2:
            assert query["csrfToken"] == ["test-public-form-token"]
        soup = BeautifulSoup(cases[slug]["list_html"], "html5lib")
        container = soup.select_one(profile.container_selector)
        assert container is not None
        if page == 2:
            container.clear()
        soup.append(
            BeautifulSoup(
                '<input name="csrfToken" value="test-public-form-token">',
                "html.parser",
            )
        )
        return str(soup)

    def get_text(
        self: RequestsHttpClient,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        assert use_session and verify_tls and headers and "Referer" in headers
        return respond(url)

    def post_text(
        self: RequestsHttpClient,
        url: str,
        *,
        data: bytes,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        assert use_session and verify_tls and headers
        assert headers["Content-Type"] == "application/x-www-form-urlencoded"
        return respond(url + "?" + data.decode("ascii"))

    monkeypatch.setattr(RequestsHttpClient, "get_text", get_text)
    monkeypatch.setattr(RequestsHttpClient, "post_text", post_text)
    expected = {
        (settings.sources[slug].municipality, case["title"], case["date"], case["url"])
        for slug, case in cases.items()
        if slug in settings.enabled_sources and "2026-10-17" <= case["date"] <= "2026-10-23"
    }
    assert len(expected) == 9
    runner = CliRunner()
    args = ["--config-path", str(config)]
    window = ["--date", "2026-10-23", "--days", "7"]
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            result = runner.invoke(app, [*args, "collect", *window])
            assert result.exit_code == 0, result.output
            assert "Skipping source" not in caplog.text
            assert set(result.stdout.splitlines()) == {n[3] for n in expected}
            with sqlite3.connect(db) as connection:
                rows = connection.execute(
                    "select municipality,title,published_date,url from notices",
                ).fetchall()
            assert len(rows) == len(expected) and set(rows) == expected
    assert seen == set(settings.enabled_sources)
    count = len(calls)
    result = runner.invoke(app, [*args, "list", *window])
    assert result.exit_code == 0
    assert set(result.stdout.splitlines()) == {n[3] for n in expected}
    assert len(calls) == count


def test_recovered_boards_collect_store_deduplicate_and_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads(
        (ROOT / "tests/fixtures/cafe_20261028_profiles.json").read_text(encoding="utf-8"),
    )
    example = ROOT / "config/batch-cafe-20261028.example.toml"
    text = example.read_text(encoding="utf-8")
    text = re.sub(
        r"^enabled_sources = .+$",
        "enabled_sources = " + json.dumps(list(cases)),
        text,
        flags=re.MULTILINE,
    )
    old = (ROOT / cases["ulsan"]["config_path"]).read_text(encoding="utf-8")
    text += old[old.index("[sources.ulsan]") : old.index("[sources.ulju]")]
    db, config = tmp_path / "notices.db", tmp_path / "config.toml"
    text = re.sub(
        r"^db_path = .+$", "db_path = " + json.dumps(db.as_posix()), text, flags=re.MULTILINE
    )
    config.write_text(
        re.sub(r"throttle_seconds = [0-9.]+", "throttle_seconds = 0.0", text), encoding="utf-8"
    )
    settings = load_config(config)
    hosts = {urlparse(c.list_url).netloc: slug for slug, c in settings.sources.items()}
    details = {case["url"]: case["detail_html"] for case in cases.values()}
    seen: set[str] = set()
    calls: list[str] = []

    def response(self: RequestsHttpClient, url: str, **kwargs: object) -> str:
        assert kwargs["verify_tls"] and kwargs["use_session"]
        calls.append(url)
        if url in details:
            return str(details[url])
        slug = hosts[urlparse(url).netloc]
        seen.add(slug)
        profile = settings.sources[slug].html_profile
        assert profile is not None
        page = int(parse_qs(urlparse(url).query).get(profile.page_param, ["1"])[0])
        assert page in {1, 2}
        soup = BeautifulSoup(cases[slug]["list_html"], "html5lib")
        if page == 2:
            container = soup.select_one(profile.container_selector)
            assert container is not None
            container.clear()
            if profile.page_number_selector:
                current = soup.select_one(profile.page_number_selector)
                assert current is not None
                current.string = "2"
        return str(soup)

    monkeypatch.setattr(RequestsHttpClient, "get_text", response)
    expected = {
        (settings.sources[slug].municipality, c["title"], c["date"], c["url"])
        for slug, c in cases.items()
    }
    runner = CliRunner()
    args = ["--config-path", str(config)]
    window = ["--date", "2026-10-28", "--days", "7"]
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            result = runner.invoke(app, [*args, "collect", *window])
            assert result.exit_code == 0, result.output
            assert "Skipping source" not in caplog.text
            assert set(result.stdout.splitlines()) == {r[3] for r in expected}
            with sqlite3.connect(db) as connection:
                rows = connection.execute(
                    "select municipality,title,published_date,url from notices",
                ).fetchall()
            assert len(rows) == len(expected) == 12 and set(rows) == expected
    assert seen == set(cases)
    before = len(calls)
    listed = runner.invoke(app, [*args, "list", *window])
    assert listed.exit_code == 0
    assert set(listed.stdout.splitlines()) == {r[3] for r in expected}
    assert len(calls) == before


def test_additional_boards_cli_collect_store_deduplicate_and_list_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fixture = json.loads(
        (ROOT / "tests/fixtures/cafe_additional_institutions.json").read_text(encoding="utf-8"),
    )
    example = ROOT / "config/batch-cafe-additional-institutions.example.toml"
    settings = load_config(example)
    config, db = tmp_path / "config.toml", tmp_path / "notices.db"
    config.write_text(
        example.read_text(encoding="utf-8")
        .replace(
            "data/cafe-additional-institutions.db",
            db.as_posix(),
        )
        .replace("throttle_seconds = 0.3", "throttle_seconds = 0.0"),
        encoding="utf-8",
    )
    details = {url: html for c in fixture["sources"].values() for url, html in c["details"].items()}
    calls: list[str] = []
    seen: set[str] = set()

    def get_text(
        self: RequestsHttpClient,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        assert verify_tls and use_session and headers and "Referer" in headers
        calls.append(url)
        if url in details:
            return str(details[url])
        parsed, query = urlparse(url), parse_qs(urlparse(url).query)
        source = next(
            s
            for s in settings.sources.values()
            if urlparse(s.list_url).netloc == parsed.netloc
            and (
                not s.slug.startswith("busan_bepa_")
                or parse_qs(urlparse(s.list_url).query)["no"] == query["no"]
            )
        )
        seen.add(source.slug)
        profile = source.html_profile
        assert profile is not None
        assert query[profile.search_param] == ["평가위원"]
        page = query[profile.page_param][0]
        return str(fixture["sources"][source.slug]["pages"][page])

    monkeypatch.setattr(RequestsHttpClient, "get_text", get_text)
    runner, args = CliRunner(), ["--config-path", str(config)]
    window = ["--date", fixture["window_end"], "--days", str(fixture["window_days"])]
    expected = {
        (n["municipality"], n["title"], n["date"], n["url"])
        for case in fixture["sources"].values()
        for n in case["notices"]
    }
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            result = runner.invoke(app, [*args, "collect", *window])
            assert result.exit_code == 0, result.output
            assert "Skipping source" not in caplog.text
            assert set(result.stdout.splitlines()) == {n[3] for n in expected}
            with sqlite3.connect(db) as connection:
                rows = connection.execute(
                    "select municipality,title,published_date,url from notices",
                ).fetchall()
            assert len(rows) == len(expected) and set(rows) == expected
    assert seen == set(settings.enabled_sources)
    assert {n["url"] for n in fixture["targets"]} <= {row[3] for row in rows}
    count = len(calls)
    listed = runner.invoke(app, [*args, "list", *window])
    assert listed.exit_code == 0
    assert set(listed.stdout.splitlines()) == {n[3] for n in expected}
    assert len(calls) == count


@pytest.mark.parametrize(
    "batch,slugs",
    [
        ("seoul-ten", ["seodaemun_gosi", "mapo_gosi"]),
        ("seoul-busan-ten", ["gangnam_union6"]),
    ],
)
def test_missing_notices_collect_store_deduplicate_and_list_offline(
    batch: str,
    slugs: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads(
        (ROOT / "tests/fixtures/cafe_four_recovered_profiles.json").read_text(encoding="utf-8"),
    )
    cases = {key: case for key, case in cases.items() if case["slug"] in slugs}
    example = ROOT / f"config/batch-{batch}.example.toml"
    settings = load_config(example)
    config, db = tmp_path / "config.toml", tmp_path / "notices.db"
    text = re.sub(
        r"^enabled_sources = .+$",
        "enabled_sources = " + json.dumps(slugs),
        example.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"^db_path = .+$", "db_path = " + json.dumps(db.as_posix()), text, flags=re.MULTILINE
    )
    config.write_text(
        text.replace("throttle_seconds = 1.0", "throttle_seconds = 0.0"), encoding="utf-8"
    )
    details = {case["url"]: case["detail_html"] for case in cases.values()}
    calls: list[str] = []
    seen: set[str] = set()

    def get_text(
        self: RequestsHttpClient,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        assert verify_tls and use_session and headers and "Referer" in headers
        calls.append(url)
        if url in details:
            return str(details[url])
        query = parse_qs(urlparse(url).query)
        source = next(
            settings.sources[slug]
            for slug in slugs
            if urlparse(settings.sources[slug].list_url).netloc == urlparse(url).netloc
        )
        seen.add(source.slug)
        profile = source.html_profile
        assert profile is not None
        assert query[profile.search_param] == ["평가위원"]
        source_cases = [case for case in cases.values() if case["slug"] == source.slug]
        soup = BeautifulSoup(source_cases[0]["list_html"], "html5lib")
        container = soup.select_one(profile.container_selector)
        assert container is not None
        if query[profile.page_param] == ["1"]:
            # Both Mapo notices have the same municipality/date and distinct article IDs.
            for case in source_cases[1:]:
                extra = BeautifulSoup(case["list_html"], "html5lib")
                extra_container = extra.select_one(profile.container_selector)
                tbody = container.select_one("tbody")
                assert extra_container is not None and tbody is not None
                for row in extra_container.select(profile.row_selector):
                    tbody.append(row)
        else:
            assert query[profile.page_param] == ["2"]
            container.clear()
        return str(soup)

    monkeypatch.setattr(RequestsHttpClient, "get_text", get_text)
    expected = {
        (settings.sources[c["slug"]].municipality, c["title"], c["date"], c["url"])
        for c in cases.values()
    }
    runner, args = CliRunner(), ["--config-path", str(config)]
    window = ["--date", "2026-10-24", "--days", "7"]
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            result = runner.invoke(app, [*args, "collect", *window])
            assert result.exit_code == 0, result.output
            assert "Skipping source" not in caplog.text
            assert set(result.stdout.splitlines()) == {n[3] for n in expected}
            with sqlite3.connect(db) as connection:
                rows = connection.execute(
                    "select municipality,title,published_date,url from notices",
                ).fetchall()
            assert len(rows) == len(expected) and set(rows) == expected
    assert seen == set(slugs)
    count = len(calls)
    listed = runner.invoke(app, [*args, "list", *window])
    assert listed.exit_code == 0
    assert set(listed.stdout.splitlines()) == {n[3] for n in expected}
    assert len(calls) == count


def test_public_institutions_cli_collect_store_deduplicate_and_list_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fixture = json.loads(
        (ROOT / "tests/fixtures/public_institutions_seven.json").read_text(encoding="utf-8"),
    )
    example = ROOT / "config/batch-public-institutions-seven.example.toml"
    settings = load_config(example)
    config, db = tmp_path / "config.toml", tmp_path / "notices.db"
    config.write_text(
        example.read_text(encoding="utf-8")
        .replace(
            "data/public-institutions-seven.db",
            db.as_posix(),
        )
        .replace("throttle_seconds = 0.3", "throttle_seconds = 0.0"),
        encoding="utf-8",
    )
    details = {
        url: html for case in fixture["sources"].values() for url, html in case["details"].items()
    }
    calls: list[str] = []
    seen: set[str] = set()

    def response(
        self: RequestsHttpClient,
        url: str,
        *,
        data: bytes | None = None,
        use_session: bool = False,
        verify_tls: bool = True,
        **kwargs: object,
    ) -> str:
        assert use_session and verify_tls
        assert "Referer" in kwargs["headers"]
        calls.append(url)
        if url in details:
            return str(details[url])
        host = urlparse(url).netloc
        source = next(s for s in settings.sources.values() if urlparse(s.list_url).netloc == host)
        seen.add(source.slug)
        profile = source.html_profile or source.json_profile
        assert profile is not None
        query = parse_qs(data.decode("ascii") if data is not None else urlparse(url).query)
        assert query[profile.search_param] == ["평가위원"]
        return str(fixture["sources"][source.slug]["pages"][query[profile.page_param][0]])

    monkeypatch.setattr(RequestsHttpClient, "get_text", response)
    monkeypatch.setattr(RequestsHttpClient, "post_text", response)
    runner, args = CliRunner(), ["--config-path", str(config)]
    window = ["--date", fixture["window_end"], "--days", str(fixture["window_days"])]
    expected = {
        (n["municipality"], n["title"], n["date"], n["url"])
        for case in fixture["sources"].values()
        for n in case["notices"]
    }
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            result = runner.invoke(app, [*args, "collect", *window])
            assert result.exit_code == 0, result.output
            assert "Skipping source" not in caplog.text
            assert set(result.stdout.splitlines()) == {n[3] for n in expected}
            with sqlite3.connect(db) as connection:
                rows = connection.execute(
                    "select municipality,title,published_date,url from notices",
                ).fetchall()
            assert len(rows) == len(expected) and set(rows) == expected
    assert seen == set(settings.enabled_sources)
    assert {n["url"] for n in fixture["targets"]} <= {n[3] for n in rows}
    count = len(calls)
    listed = runner.invoke(app, [*args, "list", *window])
    assert listed.exit_code == 0
    assert set(listed.stdout.splitlines()) == {n[3] for n in expected}
    assert len(calls) == count
