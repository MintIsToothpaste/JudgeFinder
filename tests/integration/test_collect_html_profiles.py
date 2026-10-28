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


def test_ten_sources_public_links_pagination_dedup_and_offline_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads((ROOT / "tests/fixtures/busan_daegu_ten_profiles.json").read_text())
    example = ROOT / "config/batch-busan-daegu-ten.example.toml"
    settings = load_config(example)
    db = tmp_path / "notices.db"
    config = tmp_path / "config.toml"
    config.write_text(
        example.read_text()
        .replace(
            "data/live-tests/busan-daegu-ten-2026-10-03/notices.db",
            db.as_posix(),
        )
        .replace("throttle_seconds = 1.0", "throttle_seconds = 0.0"),
        encoding="utf-8",
    )
    sources = {urlparse(s.list_url).netloc: s for s in settings.sources.values()}
    calls: list[tuple[str, str, int]] = []

    def get_text(
        self: RequestsHttpClient,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
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


def test_ten_sources_recruitment_filter_pagination_deduplication_and_offline_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads((ROOT / "tests/fixtures/daegu_incheon_ten_profiles.json").read_text())
    example = ROOT / "config/batch-daegu-incheon-ten.example.toml"
    settings = load_config(example)
    db, config = tmp_path / "notices.db", tmp_path / "config.toml"
    config.write_text(
        example.read_text()
        .replace(
            "data/live-tests/daegu-incheon-ten-2026-10-04/notices.db",
            db.as_posix(),
        )
        .replace("throttle_seconds = 1.0", "throttle_seconds = 0.0"),
        encoding="utf-8",
    )
    assert load_config(config).db_path == db
    sources = {urlparse(s.list_url).netloc: s for s in settings.sources.values()}
    calls: list[tuple[str, str, int]] = []

    def get_text(
        self: RequestsHttpClient,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
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


def test_real_profiles_pagination_exclusion_deduplication_and_offline_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads((ROOT / "tests/fixtures/gyeonggi_cities_ten_profiles.json").read_text())
    example = ROOT / "config/batch-gyeonggi-cities-ten.example.toml"
    settings = load_config(example)
    config, db = tmp_path / "config.toml", tmp_path / "notices.db"
    config.write_text(
        example.read_text()
        .replace(
            "data/live-tests/gyeonggi-cities-ten-2026-10-04/notices.db",
            db.as_posix(),
        )
        .replace("throttle_seconds = 1.0", "throttle_seconds = 0.0"),
        encoding="utf-8",
    )
    assert load_config(config).db_path == db
    details = {c["url"]: c["detail_html"] for c in cases.values() if "detail_html" in c}
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
        assert verify_tls and use_session and headers is not None and "Referer" in headers
        calls.append(url)
        if url in details:
            return str(details[url])
        parsed, query = urlparse(url), parse_qs(urlparse(url).query)

        def matches(list_url: str) -> bool:
            base, required = urlparse(list_url), parse_qs(urlparse(list_url).query)
            return (base.netloc, base.path) == (parsed.netloc, parsed.path) and all(
                query.get(k) == v for k, v in required.items()
            )

        source = next(s for s in settings.sources.values() if matches(s.list_url))
        seen.add(source.slug)
        profile, case = source.html_profile, cases[source.slug]
        assert profile is not None
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
    assert seen == set(settings.enabled_sources) and len(outputs[0].splitlines()) == 9
    with sqlite3.connect(db) as conn:
        actual = conn.execute(
            "select municipality,title,published_date,url from notices",
        ).fetchall()
    expected = [
        (settings.sources[slug].municipality, c["title"], c["date"], c["url"])
        for slug, c in cases.items()
        if c["category"] == "recruitment"
    ]
    assert sorted(actual) == sorted(expected)
    count = len(calls)
    listed = runner.invoke(app, [*args, "list", *window])
    assert listed.exit_code == 0 and listed.stdout == outputs[0] and len(calls) == count


def test_recovered_profiles_cli_pagination_dedup_and_offline_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads((ROOT / "tests/fixtures/held_eighteen_recovered_profiles.json").read_text())
    example = ROOT / "config/batch-held-eighteen.example.toml"
    settings = load_config(example)
    config, db = tmp_path / "config.toml", tmp_path / "notices.db"
    config.write_text(
        example.read_text()
        .replace(
            "data/live-tests/held-eighteen-2026-10-05/notices.db",
            db.as_posix(),
        )
        .replace("throttle_seconds = 0.3", "throttle_seconds = 0.0")
    )
    details = {c["url"]: c["detail_html"] for c in cases.values()}
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
        parsed, query = urlparse(url), parse_qs(urlparse(url).query, keep_blank_values=True)
        source = next(
            s for s in settings.sources.values() if urlparse(s.list_url).netloc == parsed.netloc
        )
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
    expected = [
        (settings.sources[slug].municipality, c["title"], c["date"], c["url"])
        for slug, c in cases.items()
    ]
    assert sorted(actual) == sorted(expected)
    count = len(calls)
    listed = runner.invoke(app, [*args, "list", *window])
    assert listed.exit_code == 0 and listed.stdout == outputs[0] and len(calls) == count


def test_ten_municipalities_recruitment_pagination_dedup_and_offline_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads((ROOT / "tests/fixtures/incheon_jeonnam_ten_profiles.json").read_text())
    example = ROOT / "config/batch-incheon-jeonnam-ten.example.toml"
    settings = load_config(example)
    db, config = tmp_path / "notices.db", tmp_path / "config.toml"
    config.write_text(
        example.read_text()
        .replace(
            "data/live-tests/incheon-jeonnam-ten-2026-10-04/notices.db",
            db.as_posix(),
        )
        .replace("throttle_seconds = 1.0", "throttle_seconds = 0.0"),
        encoding="utf-8",
    )
    assert load_config(config).db_path == db
    details = {case["url"]: case for case in cases.values() if "url" in case}
    calls: list[str] = []

    def get_text(
        self: RequestsHttpClient,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        assert verify_tls and use_session and headers is not None and "Referer" in headers
        calls.append(url)
        if url in details:
            return str(details[url]["detail_html"])
        parsed = urlparse(url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        source = next(
            s
            for s in settings.sources.values()
            if (urlparse(s.list_url).netloc, urlparse(s.list_url).path)
            == (parsed.netloc, parsed.path)
            and all(query.get(k) == v for k, v in parse_qs(s.list_url.split("?", 1)[1]).items())
        )
        profile, case = source.html_profile, cases[source.slug]
        assert profile is not None
        page = int(query[profile.page_param][0])
        assert page in (1, 2), "a repeated last page must stop pagination"
        if source.slug == "jeonnam_gwangju":
            assert "conTitle=%C6%F2%B0%A1%C0%A7%BF%F8" in url
        elif profile.search_param:
            assert query[profile.search_param] == ["평가위원"]
        return str(case.get("list_html", case.get("empty_list_html")))

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
    positive = {slug: c for slug, c in cases.items() if c.get("category") == "recruitment"}
    assert len(positive) == 9 and outputs[0] == outputs[1]
    assert len(outputs[0].splitlines()) == 9
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


def test_real_profiles_pagination_offset_deduplication_and_offline_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads((ROOT / "tests/fixtures/jeonnam_daejeon_ten_profiles.json").read_text())
    example = ROOT / "config/batch-jeonnam-daejeon-ten.example.toml"
    settings = load_config(example)
    config, db = tmp_path / "config.toml", tmp_path / "notices.db"
    config.write_text(
        example.read_text()
        .replace(
            "data/live-tests/jeonnam-daejeon-ten-2026-10-04/notices.db",
            db.as_posix(),
        )
        .replace("throttle_seconds = 1.0", "throttle_seconds = 0.0"),
        encoding="utf-8",
    )
    assert load_config(config).db_path == db
    details = {c["url"]: c["detail_html"] for c in cases.values()}
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
        assert verify_tls and use_session and headers is not None and "Referer" in headers
        calls.append(url)
        if url in details:
            return str(details[url])
        parsed, query = urlparse(url), parse_qs(urlparse(url).query)

        def matches(list_url: str) -> bool:
            base, required = urlparse(list_url), parse_qs(urlparse(list_url).query)
            return (base.netloc, base.path) == (parsed.netloc, parsed.path) and all(
                query.get(k) == v for k, v in required.items()
            )

        source = next(s for s in settings.sources.values() if matches(s.list_url))
        seen.add(source.slug)
        profile, case = source.html_profile, cases[source.slug]
        assert profile is not None
        assert query[profile.search_param] == ["평가위원"]
        page = int(query[profile.page_param][0])
        assert page in (1, 2)
        if profile.offset_param:
            assert query[profile.offset_param] == [str((page - 1) * profile.page_size)]
        if page == 1:
            return str(case["list_html"])
        if source.slug == "daejeon":
            return str(case["empty_list_html"])
        soup = BeautifulSoup(case["list_html"], "html5lib")
        container = soup.select_one(profile.container_selector)
        assert container is not None
        container.clear()
        if profile.page_number_selector:
            current = soup.select_one(profile.page_number_selector)
            assert current is not None
            current.string = "2"
        return str(soup)

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
    assert seen == set(settings.enabled_sources) and len(outputs[0].splitlines()) == 10
    with sqlite3.connect(db) as conn:
        actual = conn.execute(
            "select municipality,title,published_date,url from notices",
        ).fetchall()
    expected = [
        (settings.sources[slug].municipality, c["title"], c["date"], c["url"])
        for slug, c in cases.items()
    ]
    assert sorted(actual) == sorted(expected)
    count = len(calls)
    listed = runner.invoke(app, [*args, "list", *window])
    assert listed.exit_code == 0 and listed.stdout == outputs[0] and len(calls) == count
