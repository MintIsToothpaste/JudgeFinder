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


@pytest.mark.parametrize(
    "fixture_file",
    [
        "chungbuk_chungnam_jeonbuk_thirty_profiles.json",
        "chungbuk_chungnam_jeonbuk_recovered_profiles.json",
    ],
)
def test_chungbuk_chungnam_jeonbuk_thirty_collect_store_deduplicate_and_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    fixture_file: str,
) -> None:
    cases = json.loads(
        (ROOT / "tests/fixtures/chungbuk_chungnam_jeonbuk_thirty_profiles.json").read_text(),
    )
    cases.update(json.loads((ROOT / "tests/fixtures" / fixture_file).read_text()))
    example = ROOT / "config/batch-chungbuk-chungnam-jeonbuk-thirty.example.toml"
    settings = load_config(example)
    config, db = tmp_path / "config.toml", tmp_path / "notices.db"
    config.write_text(
        example.read_text()
        .replace(
            "data/live-tests/chungbuk-chungnam-jeonbuk-thirty-2026-10-05/notices.db",
            db.as_posix(),
        )
        .replace("throttle_seconds = 0.3", "throttle_seconds = 0.0")
    )
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

        def matches(source) -> bool:
            base = urlparse(source.list_url)
            required = parse_qs(base.query)
            required.pop((source.html_profile or source.json_profile).page_param, None)
            return (base.netloc, base.path) == (parsed.netloc, parsed.path) and all(
                query.get(k) == v for k, v in required.items()
            )

        source = next(s for s in settings.sources.values() if matches(s))
        seen.add(source.slug)
        profile, case = source.html_profile or source.json_profile, cases[source.slug]
        assert profile is not None
        assert query[profile.search_param] == ["평가위원"]
        page = int(query[profile.page_param][0])
        assert page in (1, 2)
        if source.json_profile:
            data = json.loads(case["list_json"])
            if page == 2:
                data["noticeList"] = []
            return json.dumps(data)
        if page == 1:
            return str(case["list_html"])
        soup = BeautifulSoup(case["list_html"], "html5lib")
        container = soup.select_one(source.html_profile.container_selector)
        assert container is not None
        for row in container.select(source.html_profile.row_selector):
            row.decompose()
        if source.html_profile.page_number_selector:
            current = soup.select_one(source.html_profile.page_number_selector)
            assert current is not None
            current.string = "2"
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
    assert seen == set(settings.enabled_sources) and len(outputs[0].splitlines()) == 28
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


def test_actual_html_json_post_pagination_dedupe_and_offline_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads(
        (ROOT / "tests/fixtures/daejeon_ulsan_sejong_gyeonggi_ten_profiles.json").read_text(),
    )
    example = ROOT / "config/batch-daejeon-ulsan-sejong-gyeonggi-ten.example.toml"
    settings = load_config(example)
    config, db = tmp_path / "config.toml", tmp_path / "notices.db"
    config.write_text(
        example.read_text()
        .replace(
            "data/live-tests/daejeon-ulsan-sejong-gyeonggi-ten-2026-10-04/notices.db",
            db.as_posix(),
        )
        .replace("throttle_seconds = 1.0", "throttle_seconds = 0.0"),
        encoding="utf-8",
    )
    assert load_config(config).db_path == db
    details = {c["url"]: c["detail_html"] for c in cases.values() if "url" in c}
    calls: list[tuple[str, str]] = []
    seen: set[str] = set()

    def response(url: str, method: str) -> str:
        calls.append((method, url))
        if url in details:
            assert method == "GET"
            return str(details[url])
        parsed, query = urlparse(url), parse_qs(urlparse(url).query)

        def matches(list_url: str) -> bool:
            base, required = urlparse(list_url), parse_qs(urlparse(list_url).query)
            return (base.netloc, base.path) == (parsed.netloc, parsed.path) and all(
                query.get(k) == v for k, v in required.items()
            )

        source = next(s for s in settings.sources.values() if matches(s.list_url))
        assert source.slug in settings.enabled_sources
        seen.add(source.slug)
        profile, case = source.html_profile or source.json_profile, cases[source.slug]
        assert profile is not None and profile.request_method == method
        assert query[profile.search_param] == ["평가위원"]
        page = int(query[profile.page_param][0])
        assert page in (1, 2)
        if source.json_profile:
            assert query[profile.offset_param] == [str((page - 1) * profile.page_size)]
            return str(case["list_json"]) if page == 1 else '{"total":1,"items":[]}'
        profile = source.html_profile
        assert profile is not None
        if page == 1:
            return str(case["list_html"])
        soup = BeautifulSoup(case["list_html"], "html5lib")
        container = soup.select_one(profile.container_selector)
        assert container is not None
        container.clear()
        if profile.page_number_selector:
            current = soup.select_one(profile.page_number_selector)
            assert current is not None
            current.string = "2"
        return str(soup)

    def get_text(
        self: RequestsHttpClient,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        assert verify_tls and use_session and headers is not None and "Referer" in headers
        return response(url, "GET")

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
        assert verify_tls and use_session and headers is not None and "Referer" in headers
        return response(url + "?" + data.decode("ascii"), "POST")

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
    assert seen == set(settings.enabled_sources) and len(outputs[0].splitlines()) == 9
    with sqlite3.connect(db) as conn:
        actual = conn.execute(
            "select municipality,title,published_date,url from notices",
        ).fetchall()
    expected = [
        (settings.sources[s].municipality, cases[s]["title"], cases[s]["date"], cases[s]["url"])
        for s in settings.enabled_sources
    ]
    assert sorted(actual) == sorted(expected)
    count = len(calls)
    listed = runner.invoke(app, [*args, "list", *window])
    assert listed.exit_code == 0 and listed.stdout == outputs[0] and len(calls) == count


def test_gyeonggi_gangwon_chungbuk_thirty_collect_store_deduplicate_and_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads(
        (ROOT / "tests/fixtures/gyeonggi_gangwon_chungbuk_thirty_profiles.json").read_text(),
    )
    example = ROOT / "config/batch-gyeonggi-gangwon-chungbuk-thirty.example.toml"
    settings = load_config(example)
    config, db = tmp_path / "config.toml", tmp_path / "notices.db"
    config.write_text(
        example.read_text()
        .replace(
            "data/live-tests/gyeonggi-gangwon-chungbuk-thirty-2026-10-05/notices.db",
            db.as_posix(),
        )
        .replace("throttle_seconds = 0.3", "throttle_seconds = 0.0")
    )
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

        def matches(source) -> bool:
            base = urlparse(source.list_url)
            required = parse_qs(base.query)
            required.pop((source.html_profile or source.json_profile).page_param, None)
            return (base.netloc, base.path) == (parsed.netloc, parsed.path) and all(
                query.get(k) == v for k, v in required.items()
            )

        source = next(s for s in settings.sources.values() if matches(s))
        seen.add(source.slug)
        profile, case = source.html_profile or source.json_profile, cases[source.slug]
        assert profile is not None
        expected_search = parse_qs(urlparse(source.list_url).query).get(
            profile.search_param,
            ["평가위원"],
        )
        assert query[profile.search_param] == expected_search
        page = int(query[profile.page_param][0])
        assert page in (1, 2)
        if source.json_profile:
            data = json.loads(case["list_json"])
            if page == 2:
                data["noticeList"] = []
            return json.dumps(data)
        if page == 1:
            return str(case["list_html"])
        soup = BeautifulSoup(case["list_html"], "html5lib")
        container = soup.select_one(source.html_profile.container_selector)
        assert container is not None
        for row in container.select(source.html_profile.row_selector):
            row.decompose()
        if source.html_profile.page_number_selector:
            current = soup.select_one(source.html_profile.page_number_selector)
            assert current is not None
            current.string = "2"
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
    assert seen == set(settings.enabled_sources) and len(outputs[0].splitlines()) == 28
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


def test_actual_profiles_cli_pagination_dedup_and_offline_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads((ROOT / "tests/fixtures/gyeongnam_jeju_final_profiles.json").read_text())
    example = ROOT / "config/batch-gyeongnam-jeju-final-twenty.example.toml"
    settings = load_config(example)
    config, db = tmp_path / "config.toml", tmp_path / "notices.db"
    config.write_text(
        example.read_text()
        .replace(
            "data/live-tests/gyeongnam-jeju-final-twenty-2026-10-05/notices.db",
            db.as_posix(),
        )
        .replace("throttle_seconds = 0.3", "throttle_seconds = 0.0")
    )
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
        parsed, query = urlparse(url), parse_qs(urlparse(url).query, keep_blank_values=True)

        def matches(source) -> bool:
            base = urlparse(source.list_url)
            required = parse_qs(base.query, keep_blank_values=True)
            required.pop((source.html_profile or source.json_profile).page_param, None)
            return (base.netloc, base.path) == (parsed.netloc, parsed.path) and all(
                query.get(k) == v for k, v in required.items()
            )

        source = next(s for s in settings.sources.values() if matches(s))
        seen.add(source.slug)
        profile, case = source.html_profile or source.json_profile, cases[source.slug]
        assert query[profile.search_param] == ["평가위원"]
        page = int(query[profile.page_param][0])
        assert page in (1, 2)
        if source.json_profile:
            data = json.loads(case["list_json"])
            data["query"]["page"] = page
            if page == 2:
                data["gosis"] = []
            return json.dumps(data)
        if page == 1:
            return str(case["list_html"])
        soup = BeautifulSoup(case["list_html"], "html5lib")
        container = soup.select_one(source.html_profile.container_selector)
        assert container is not None
        for row in container.select(source.html_profile.row_selector):
            row.decompose()
        if source.html_profile.page_number_selector:
            current = soup.select_one(source.html_profile.page_number_selector)
            assert current is not None
            current.string = "2"
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
    assert len(outputs[0].splitlines()) == 21
    with sqlite3.connect(db) as conn:
        actual = conn.execute(
            "select municipality,title,published_date,url from notices",
        ).fetchall()
    expected = [
        (settings.sources[slug].municipality, c["title"], c["date"], c["url"])
        for slug, c in cases.items()
        if not c.get("empty")
    ]
    assert sorted(actual) == sorted(expected)
    count = len(calls)
    listed = runner.invoke(app, [*args, "list", *window])
    assert listed.exit_code == 0 and listed.stdout == outputs[0] and len(calls) == count


@pytest.mark.parametrize(
    "fixture_file",
    [
        "jeonbuk_gyeongbuk_gyeongnam_thirty_profiles.json",
        "jeonbuk_gyeongbuk_gyeongnam_recovered_profiles.json",
    ],
)
def test_jeonbuk_gyeongbuk_gyeongnam_thirty_collect_store_deduplicate_and_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    fixture_file: str,
) -> None:
    cases = json.loads(
        (ROOT / "tests/fixtures/jeonbuk_gyeongbuk_gyeongnam_thirty_profiles.json").read_text(),
    )
    originals = dict(cases)
    cases.update(json.loads((ROOT / "tests/fixtures" / fixture_file).read_text()))
    example = ROOT / "config/batch-jeonbuk-gyeongbuk-gyeongnam-thirty.example.toml"
    settings = load_config(example)
    config, db = tmp_path / "config.toml", tmp_path / "notices.db"
    config.write_text(
        example.read_text()
        .replace(
            "data/live-tests/jeonbuk-gyeongbuk-gyeongnam-thirty-2026-10-05/notices.db",
            db.as_posix(),
        )
        .replace("throttle_seconds = 0.3", "throttle_seconds = 0.0")
    )
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

        def matches(source) -> bool:
            base = urlparse(source.list_url)
            required = parse_qs(base.query)
            required.pop((source.html_profile or source.json_profile).page_param, None)
            return (base.netloc, base.path) == (parsed.netloc, parsed.path) and all(
                query.get(k) == v for k, v in required.items()
            )

        source = next(s for s in settings.sources.values() if matches(s))
        seen.add(source.slug)
        profile, case = source.html_profile or source.json_profile, cases[source.slug]
        assert profile is not None
        assert query[profile.search_param] == ["평가위원"]
        page = int(query[profile.page_param][0])
        assert page in (1, 2)
        if source.json_profile:
            data = json.loads(case["list_json"])
            if page == 2:
                data["noticeList"] = []
            return json.dumps(data)
        if page == 1:
            listing = str(case["list_html"])
            current_selector = source.html_profile.page_number_selector
            if current_selector and not BeautifulSoup(listing, "html5lib").select_one(
                current_selector,
            ):
                original = BeautifulSoup(originals[source.slug]["list_html"], "html5lib")
                listing += str(original.select_one(current_selector).parent)
            return listing
        soup = BeautifulSoup(originals[source.slug]["list_html"], "html5lib")
        container = soup.select_one(source.html_profile.container_selector)
        assert container is not None
        for row in container.select(source.html_profile.row_selector):
            row.decompose()
        if source.html_profile.page_number_selector:
            current = soup.select_one(source.html_profile.page_number_selector)
            assert current is not None
            current.string = "2"
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
    assert seen == set(settings.enabled_sources) and len(outputs[0].splitlines()) == 25
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


def test_real_profiles_collection_pagination_deduplication_and_offline_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads((ROOT / "tests/fixtures/jeonnam_gwangju_ten_profiles.json").read_text())
    example = ROOT / "config/batch-jeonnam-gwangju-ten.example.toml"
    settings = load_config(example)
    config, db = tmp_path / "config.toml", tmp_path / "notices.db"
    config.write_text(
        example.read_text()
        .replace(
            "data/live-tests/jeonnam-gwangju-ten-2026-10-04/notices.db",
            db.as_posix(),
        )
        .replace("throttle_seconds = 1.0", "throttle_seconds = 0.0"),
        encoding="utf-8",
    )
    assert load_config(config).db_path == db
    details = {case["url"]: case for case in cases.values() if "detail_html" in case}
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
        parsed, query = urlparse(url), parse_qs(urlparse(url).query)
        source = next(
            s
            for s in settings.sources.values()
            if (urlparse(s.list_url).netloc, urlparse(s.list_url).path)
            == (parsed.netloc, parsed.path)
            and all(query.get(k) == v for k, v in parse_qs(urlparse(s.list_url).query).items())
        )
        profile, case = source.html_profile or source.json_profile, cases[source.slug]
        assert profile is not None
        page = int(query[profile.page_param][0])
        assert page in (1, 2)
        if source.json_profile:
            assert query["BEGIN_ROW_IDX"] == [str((page - 1) * 10 + 1)]
            data = json.loads(case["list_json"])
            if page == 2:
                data["RSLT_DATA"]["searchList"]["pageMap"]["nowPage"] = "2"
                data["RSLT_DATA"]["searchList"]["dataMap"] = []
            return json.dumps(data, ensure_ascii=False)
        if source.slug == "suncheon" and page == 2:
            return (
                '<table class="bbsList"><tbody><tr><td>검색 결과가 없습니다.</td></tr>'
                '</tbody></table><a class="on" title="현재페이지">2</a>'
            )
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
    assert "Skipping source" not in caplog.text and outputs[0] == outputs[1]
    positive = {slug: c for slug, c in cases.items() if c.get("category") == "recruitment"}
    assert len(positive) == 10 and len(outputs[0].splitlines()) == 10
    with sqlite3.connect(db) as conn:
        actual = conn.execute(
            "select municipality,title,published_date,url from notices order by municipality",
        ).fetchall()
    assert actual == sorted(
        (settings.sources[slug].municipality, c["title"], c["date"], c["url"])
        for slug, c in positive.items()
    )
    count = len(calls)
    listed = runner.invoke(app, [*args, "list", *window])
    assert listed.exit_code == 0 and listed.stdout == outputs[0] and len(calls) == count
