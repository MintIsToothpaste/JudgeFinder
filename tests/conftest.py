from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from bs4 import BeautifulSoup

from judgefinder.adapters.config import load_config
from judgefinder.infrastructure.http.client import RequestsHttpClient
from judgefinder.infrastructure.http.windows_curl import WindowsCurlHttpClient

ROOT = Path(__file__).parents[1]


@pytest.fixture
def wonkwang_contract_case() -> dict[str, str]:
    return json.loads((ROOT / "tests/fixtures/wonkwang_contract.json").read_text(encoding="utf-8"))


@pytest.fixture
def wonkwang_contract_http(
    wonkwang_contract_case: dict[str, str], monkeypatch: pytest.MonkeyPatch,
) -> list[str]:
    case = wonkwang_contract_case
    base = "https://intra.wku.ac.kr/services/contract/cntrc.jsp"
    calls: list[str] = []
    context: dict[str, str] = {}

    def remember(payload: str) -> str:
        soup = BeautifulSoup(payload, "html5lib")
        context.update({str(e["name"]): str(e.get("value", ""))
                        for e in soup.select('input[name="g_secure"],input[name="g_accountyear"]')})
        return payload

    def get(self: RequestsHttpClient, url: str, **kwargs: object) -> str:
        assert url == base and kwargs["use_session"] and kwargs["verify_tls"]
        calls.append("GET " + url)
        return remember(case["seed_html"])

    def post(self: RequestsHttpClient, url: str, *, data: bytes, **kwargs: object) -> str:
        assert kwargs["use_session"] and kwargs["verify_tls"]
        assert "?" not in url and url in {base, base.replace("cntrc.jsp", "cntrc_read.jsp")}
        calls.append("POST " + url)
        fields = parse_qs(data.decode("ascii"), keep_blank_values=True)
        assert fields["g_secure"] == [context["g_secure"]]
        assert fields["g_accountyear"] == [context["g_accountyear"]]
        if url == base:
            assert fields["skeyword"] == ["평가위원"] and fields["notice_no"] == [""]
            payload = case["list_html"]
            if fields["page"] == ["2"]:
                payload = case["empty_html"]
        else:
            assert fields["notice_no"] == parse_qs(urlparse(case["url"]).query)["notice_no"]
            payload = case["detail_html"]
        return remember(payload)

    monkeypatch.setattr(RequestsHttpClient, "get_text", get)
    monkeypatch.setattr(RequestsHttpClient, "post_text", post)
    return calls


RECOVERED_BOARDS = {
    slug: case
    for filename in (
        "cafe_20261022_profiles.json", "cafe_20261021_profiles.json",
        "cafe_20261029_profiles.json", "hibrain_profiles.json", "cafe_20261030_profiles.json",
        "hibrain_routes_profiles.json", "cafe_20261031_profiles.json",
        "cafe_20261103_profiles.json",
        "cafe_20261104_profiles.json", "cafe_20261105_profiles.json", "cafe_20261106_profiles.json",
        "cafe_20261109_profiles.json", "cafe_20261110_profiles.json",
        "hibrain_20261110_profiles.json", "cafe_20261112_profiles.json",
        "cafe_20261113_profiles.json", "cafe_20261118_profiles.json",
    )
    for slug, case in json.loads(
        (ROOT / "tests/fixtures" / filename).read_text(encoding="utf-8"),
    ).items()
    if "list_html" in case
}


@pytest.fixture(params=sorted(RECOVERED_BOARDS))
def recovered_board_case(request: pytest.FixtureRequest) -> dict[str, str]:
    slug = str(request.param)
    return {"slug": slug, **RECOVERED_BOARDS[slug]}


@pytest.fixture
def recovered_board_http(
    recovered_board_case: dict[str, str], monkeypatch: pytest.MonkeyPatch,
) -> list[str]:
    """Share captured board responses between parser/source and CLI tests."""
    case = recovered_board_case
    config = load_config(ROOT / case["config_path"]).sources[case["slug"]]
    profile = config.html_profile
    assert profile is not None
    calls: list[str] = []

    def response(
        self: RequestsHttpClient | WindowsCurlHttpClient, url: str, **kwargs: object,
    ) -> str:
        assert kwargs["verify_tls"]
        assert "Chrome/" in kwargs["headers"]["User-Agent"]
        assert kwargs["use_session"] == config.request_strategy.session
        data = kwargs.get("data")
        if isinstance(data, bytes):
            assert profile.request_method == "POST"
            url += "?" + data.decode("ascii")
        calls.append(url)
        if url == case["url"]:
            return case["detail_html"]
        query = parse_qs(urlparse(url).query)
        if profile.search_param:
            assert query[profile.search_param] == [case.get("search_keyword", "평가위원")]
        if profile.page_path_template:
            page = int(urlparse(url).path.rsplit("/", 1)[1])
        elif profile.offset_param:
            page = int(query[profile.offset_param][0]) // profile.page_size + 1
        else:
            page = int(query[profile.page_param][0])
        assert page in {1, 2}
        if page == 1:
            return case["list_html"]
        if "empty_html" in case:
            return case["empty_html"]
        soup = BeautifulSoup(case["list_html"], "html5lib")
        container = soup.select_one(profile.container_selector)
        assert container is not None
        for row in container.select(profile.row_selector):
            row.decompose()
        if profile.page_number_selector:
            current = soup.select_one(profile.page_number_selector)
            assert current is not None
            current.string = "2"
        return str(soup)

    monkeypatch.setattr(RequestsHttpClient, "get_text", response)
    monkeypatch.setattr(RequestsHttpClient, "post_text", response)
    monkeypatch.setattr(WindowsCurlHttpClient, "get_text", response)
    monkeypatch.setattr(WindowsCurlHttpClient, "post_text", response)
    return calls
