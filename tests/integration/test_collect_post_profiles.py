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


def test_ten_busan_sources_native_post_repeated_pages_dedup_and_offline_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads((ROOT / "tests/fixtures/busan_ten_profiles.json").read_text())
    example = ROOT / "config/batch-busan-ten.example.toml"
    settings = load_config(example)
    db = tmp_path / "notices.db"
    config = tmp_path / "config.toml"
    config.write_text(
        example.read_text()
        .replace(
            "data/live-tests/busan-ten-2026-10-03/notices.db",
            db.as_posix(),
        )
        .replace("throttle_seconds = 1.0", "throttle_seconds = 0.0"),
        encoding="utf-8",
    )
    sources = {urlparse(s.list_url).netloc: s for s in settings.sources.values()}
    calls: list[tuple[str, str, int]] = []

    def response(url: str, *, method: str) -> str:
        source = sources[urlparse(url).netloc]
        case = cases[source.slug]
        if url == case["url"]:
            assert method == "GET"
            calls.append((source.slug, "detail", 0))
            return str(case["detail_html"])
        profile = source.html_profile
        assert profile is not None and profile.request_method == method
        query = parse_qs(urlparse(url).query)
        assert query[profile.search_param] == ["평가위원"]
        assert query["list_gubun"] == ["A"]
        if source.slug == "busanjin":
            assert query["epcCheck"] == ["Y"]
        page = int(query[profile.page_param][0])
        assert page in (1, 2), "an out-of-range page clamped to page one must stop pagination"
        calls.append((source.slug, "list", page))
        return str(case["list_html"])

    def get_text(
        self: RequestsHttpClient,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        assert verify_tls and use_session and headers is not None and "Referer" in headers
        return response(url, method="GET")

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
        assert verify_tls and use_session and headers is not None
        assert headers["Content-Type"] == "application/x-www-form-urlencoded"
        assert "Referer" in headers and not urlparse(url).query
        return response(url + "?" + data.decode("ascii"), method="POST")

    monkeypatch.setattr(RequestsHttpClient, "get_text", get_text)
    monkeypatch.setattr(RequestsHttpClient, "post_text", post_text)
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


def test_real_profiles_pagination_exclusion_deduplication_and_offline_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads((ROOT / "tests/fixtures/gyeonggi_cities_next_ten_profiles.json").read_text())
    example = ROOT / "config/batch-gyeonggi-cities-next-ten.example.toml"
    settings = load_config(example)
    config, db = tmp_path / "config.toml", tmp_path / "notices.db"
    config.write_text(
        example.read_text()
        .replace(
            "data/live-tests/gyeonggi-cities-next-ten-2026-10-04/notices.db",
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
        _post: bool = False,
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
        self: RequestsHttpClient,
        url: str,
        data: bytes,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        assert data.isascii()
        return get_text(
            self,
            url + "?" + data.decode("ascii"),
            timeout_seconds=timeout_seconds,
            headers=headers,
            use_session=use_session,
            verify_tls=verify_tls,
            _post=True,
        )

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
    expected = [
        (settings.sources[slug].municipality, c["title"], c["date"], c["url"])
        for slug, c in cases.items()
        if c["category"] == "recruitment"
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
    cases = json.loads((ROOT / "tests/fixtures/jeonnam_counties_ten_profiles.json").read_text())
    nomination = json.loads((ROOT / "tests/fixtures/gangjin_nomination_profile.json").read_text())
    example = ROOT / "config/batch-jeonnam-counties-ten.example.toml"
    settings = load_config(example)
    config, db = tmp_path / "config.toml", tmp_path / "notices.db"
    config.write_text(
        example.read_text()
        .replace(
            "data/live-tests/jeonnam-counties-ten-2026-10-04/notices.db",
            db.as_posix(),
        )
        .replace("throttle_seconds = 1.0", "throttle_seconds = 0.0"),
        encoding="utf-8",
    )
    assert load_config(config).db_path == db
    details = {case["url"]: case for case in cases.values() if "detail_html" in case}
    details[nomination["gangjin"]["url"]] = nomination["gangjin"]
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
            return str(details[url]["detail_html"])
        parsed, query = urlparse(url), parse_qs(urlparse(url).query)

        def matches(list_url: str) -> bool:
            base, required = urlparse(list_url), parse_qs(urlparse(list_url).query)
            return (
                (base.netloc, base.path) == (parsed.netloc, parsed.path)
                and all(query.get(k) == v for k, v in required.items())
                and query.get("category_1", [""]) == required.get("category_1", [""])
            )

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
                return (
                    '<table class="board_list"><tbody></tbody></table>'
                    '<li class="current"><a>2</a></li>'
                )
            if source.slug == "haenam":
                return (
                    '<table class="board_list"><tbody></tbody></table>'
                    '<div class="pagination"><a class="select">2</a></div>'
                )
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
    expected = [
        (settings.sources[slug].municipality, c["title"], c["date"], c["url"])
        for slug, c in positive.items()
    ]
    c = nomination["gangjin"]
    expected.append((settings.sources["gangjin"].municipality, c["title"], c["date"], c["url"]))
    assert sorted(actual) == sorted(expected)
    count = len(calls)
    listed = runner.invoke(app, [*args, "list", *window])
    assert listed.exit_code == 0 and listed.stdout == outputs[0] and len(calls) == count


def test_ten_html_sources_cli_repeated_collect_and_offline_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads((ROOT / "tests/fixtures/seoul_busan_ten_profiles.json").read_text())
    recovered = json.loads(
        (ROOT / "tests/fixtures/cafe_five_recovered_profiles.json").read_text(encoding="utf-8"),
    )
    cases.update({slug: recovered[slug] for slug in ("seocho_katia", "busan_gosi")})
    extra = json.loads(
        (ROOT / "tests/fixtures/cafe_four_recovered_profiles.json").read_text(encoding="utf-8"),
    )
    cases.update({slug: extra[slug] for slug in ("gangnam_union6",)})
    example = ROOT / "config/batch-seoul-busan-ten.example.toml"
    settings = load_config(example)
    db = tmp_path / "notices.db"
    config = tmp_path / "config.toml"
    config.write_text(
        example.read_text()
        .replace("data/live-tests/seoul-busan-ten-2026-09-30/notices.db", db.as_posix())
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
        assert verify_tls and use_session
        host = urlparse(url).netloc
        if host == "www.busan.go.kr":
            source = settings.sources[
                "busan_gosi" if urlparse(url).path.startswith("/nbgosi") else "busan"
            ]
        elif host == "www.gangnam.go.kr":
            source = settings.sources[
                "gangnam_union6" if urlparse(url).path.startswith("/board/union6/") else "gangnam"
            ]
        else:
            source = sources[host]
        case = cases[source.slug]
        if url == case["url"]:
            calls.append((source.slug, "detail", 0))
            return str(case["detail_html"])
        profile = source.html_profile
        assert profile is not None
        query = parse_qs(urlparse(url).query)
        expected_search = parse_qs(urlparse(source.list_url).query).get(
            profile.search_param,
            ["평가위원"],
        )
        assert query[profile.search_param] == expected_search
        if "list_gubun" in query:
            assert query["list_gubun"] == ["A"]
        if source.slug == "gangdong":
            assert query["epcCheck"] == ["Y"]
        page = int(query[profile.page_param][0])
        calls.append((source.slug, "list", page))
        soup = BeautifulSoup(case["list_html"], "html5lib")
        if page > 1:
            container = soup.select_one(profile.container_selector)
            assert container is not None
            container.clear()
            empty = BeautifulSoup(
                '<table><tbody><tr><td colspan="100%"><div class="empty-list">'
                '<div class="center">결과가 없습니다.</div></div></td></tr></tbody></table>',
                "html5lib",
            ).find("tbody")
            assert empty is not None
            container.append(empty)
        return str(soup)

    monkeypatch.setattr(RequestsHttpClient, "get_text", get_text)
    runner = CliRunner()
    args = ["--config-path", str(config)]
    window = ["--date", "2026-10-27", "--days", "400"]
    outputs = []
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            result = runner.invoke(app, [*args, "collect", *window])
            assert result.exit_code == 0, result.output
            outputs.append(result.stdout)
    assert "Skipping source" not in caplog.text
    assert outputs[0] == outputs[1]
    assert len(outputs[0].splitlines()) == len(cases)
    with sqlite3.connect(db) as conn:
        actual = conn.execute(
            "SELECT municipality,title,published_date,url FROM notices "
            "ORDER BY municipality, title, published_date, url",
        ).fetchall()
    assert actual == sorted(
        (settings.sources[slug].municipality, case["title"], case["date"], case["url"])
        for slug, case in cases.items()
    )
    for slug in cases:
        assert sum(s == slug and kind == "detail" for s, kind, _ in calls) == 2
        assert sum(s == slug and kind == "list" for s, kind, _ in calls) == 4
    before = len(calls)
    result = runner.invoke(app, [*args, "list", *window])
    assert result.exit_code == 0 and result.stdout == outputs[0]
    assert len(calls) == before


def test_ten_sources_cli_dates_detail_enrichment_and_sqlite_dedup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads(
        (ROOT / "tests/fixtures/seoul_ten_profiles.json").read_text(encoding="utf-8"),
    )
    recovered = json.loads(
        (ROOT / "tests/fixtures/cafe_five_recovered_profiles.json").read_text(encoding="utf-8"),
    )
    cases.update({slug: recovered[slug] for slug in ("yangcheon_gosi", "gangbuk_gosi")})
    extra = json.loads(
        (ROOT / "tests/fixtures/cafe_four_recovered_profiles.json").read_text(encoding="utf-8"),
    )
    cases.update({slug: extra[slug] for slug in ("seodaemun_gosi", "mapo_gosi")})
    hibrain = json.loads(
        (ROOT / "tests/fixtures/hibrain_profiles.json").read_text(encoding="utf-8"),
    )
    cases["nowon_gosi"] = hibrain["nowon_gosi"]
    example = ROOT / "config/batch-seoul-ten.example.toml"
    settings = load_config(example)
    db = tmp_path / "notices.db"
    config = tmp_path / "config.toml"
    config.write_text(
        example.read_text(encoding="utf-8")
        .replace("data/live-tests/seoul-ten-2026-09-27/notices.db", db.as_posix())
        .replace("throttle_seconds = 1.0", "throttle_seconds = 0.0"),
        encoding="utf-8",
    )
    by_host = {
        urlparse(s.list_url).netloc: s
        for s in settings.sources.values() if s.slug != "nowon_gosi"
    }
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
        self: RequestsHttpClient,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        source = by_host[urlparse(url).netloc]
        # Nowon news and public notices share a host but have different board IDs.
        if source.slug == "nowon" and parse_qs(urlparse(url).query).get("q_bbsCode") == ["1003"]:
            source = settings.sources["nowon_gosi"]
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
        self: RequestsHttpClient,
        url: str,
        *,
        data: bytes,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
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
        hits = (
            [
                {
                    "_source": {
                        "ba_title": case["title"],
                        "ba_regdate": case["date"],
                        "link_url": urlparse(case["url"]).path + "?cp=1",
                    }
                }
            ]
            if page == 1
            else []
        )
        return json.dumps({"responses": [{"hits": {"hits": hits}}]})

    monkeypatch.setattr(RequestsHttpClient, "get_text", get_text)
    monkeypatch.setattr(RequestsHttpClient, "post_text", post_text)
    runner = CliRunner()
    base = ["--config-path", str(config)]
    outputs = []
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            result = runner.invoke(app, [*base, "collect", "--date", "2026-10-27", "--days", "400"])
            assert result.exit_code == 0, result.output
            outputs.append(result.stdout)
    assert "Skipping source" not in caplog.text
    assert outputs[0] == outputs[1]
    assert len(outputs[0].splitlines()) == len(cases)
    with sqlite3.connect(db) as conn:
        actual = conn.execute(
            "SELECT municipality, title, published_date, url FROM notices "
            "ORDER BY municipality, title, published_date, url",
        ).fetchall()
    expected = sorted(
        [
            (settings.sources[slug].municipality, case["title"], case["date"], case["url"])
            for slug, case in cases.items()
        ]
    )
    assert actual == expected
    for slug in settings.sources:
        assert sum(s == slug and kind != "detail" for s, kind, _ in calls) == 4
        assert sum(s == slug and kind == "detail" for s, kind, _ in calls) == (
            2 if cases[slug]["detail_html"] else 0
        )
    before = len(calls)
    result = runner.invoke(app, [*base, "list", "--date", "2026-10-27", "--days", "400"])
    assert result.exit_code == 0
    assert result.stdout == outputs[0]
    assert len(calls) == before


def test_five_profiles_through_cli_with_pagination_and_sqlite_dedup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    example = ROOT / "config/batch-seoul-five.example.toml"
    settings = load_config(example)
    config = tmp_path / "config.toml"
    db = tmp_path / "notices.db"
    config.write_text(
        example.read_text(encoding="utf-8")
        .replace("data/live-tests/batch-2026-09-27/notices.db", db.as_posix())
        .replace("throttle_seconds = 1.0", "throttle_seconds = 0.0"),
        encoding="utf-8",
    )
    by_host = {urlparse(s.list_url).netloc: s for s in settings.sources.values()}
    calls: list[tuple[str, int]] = []

    def get_text(
        self: RequestsHttpClient,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
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
    assert actual == sorted(
        [
            ("서울특별시", "2026-08-05", "html"),
            ("종로구", "2026-09-21", "html"),
            ("서울 중구", "2026-04-08", "html"),
            ("용산구", "2026-07-22", "html"),
            ("성동구", "2026-09-22", "html"),
        ]
    )
    result = runner.invoke(app, [*base, "list", "--date", "2026-09-27", "--days", "180"])
    assert result.exit_code == 0
    assert result.stdout == outputs[0]
    assert len(calls) == 20
