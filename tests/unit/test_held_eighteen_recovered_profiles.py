import json
import re
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest
from bs4 import BeautifulSoup, Comment

from judgefinder.adapters.config import load_config
from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html

ROOT = Path(__file__).parents[2]
CASES = json.loads((ROOT / "tests/fixtures/held_eighteen_recovered_profiles.json").read_text())
SETTINGS = load_config(ROOT / "config/batch-held-eighteen.example.toml")


@pytest.mark.parametrize("slug", CASES)
def test_actual_full_title_registration_date_and_url(slug: str) -> None:
    source, case = SETTINGS.sources[slug], CASES[slug]
    loader = Mock(return_value=case["detail_html"])
    actual = parse_profiled_html(
        case["list_html"], list_url=source.list_url, profile=source.html_profile,
        detail_loader=loader, expected_page=1, recruitment_only=True,
    )
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]
    loader.assert_called_once_with(case["url"])


@pytest.mark.parametrize("slug", CASES)
def test_missing_detail_remains_a_failure(slug: str) -> None:
    source, case = SETTINGS.sources[slug], CASES[slug]
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            case["list_html"], list_url=source.list_url, profile=source.html_profile,
            detail_loader=Mock(return_value="<h1>Blocked</h1>"),
        )


@pytest.mark.parametrize("slug", CASES)
def test_page_mismatch_fails_before_requesting_details(slug: str) -> None:
    source, loader = SETTINGS.sources[slug], Mock()
    with pytest.raises(ValueError, match="page does not match"):
        parse_profiled_html(
            CASES[slug]["list_html"], list_url=source.list_url,
            profile=source.html_profile, expected_page=2, detail_loader=loader,
        )
    loader.assert_not_called()


def test_pyeongchang_does_not_use_posting_period_as_registration_date() -> None:
    source, case = SETTINGS.sources["pyeongchang"], CASES["pyeongchang"]
    assert source.html_profile.detail_origin == "https://www.pc.go.kr"
    assert not source.html_profile.detail_date_selector
    actual = parse_profiled_html(
        case["list_html"], list_url=source.list_url, profile=source.html_profile,
        detail_loader=Mock(return_value=case["detail_html"] + "<p>게시기간 2000-01-01</p>"),
    )
    assert str(actual[0].published_date) == case["date"]
    with pytest.raises(ValueError, match="configured host"):
        parse_profiled_html(
            case["list_html"], list_url=source.list_url,
            profile=replace(source.html_profile, detail_origin=""),
        )


def test_only_recovered_sources_are_enabled_and_tls_is_preserved() -> None:
    assert set(SETTINGS.enabled_sources) == set(CASES) == {
        "pyeongchang", "sangju", "andong", "namyangju",
    }
    assert "isLinkage=Y" in SETTINGS.sources["andong"].html_profile.detail_url_template
    assert "list_gubun=A" in SETTINGS.sources["sangju"].list_url
    for source in SETTINGS.sources.values():
        assert source.fixture_path is None and source.recruitment_only
        assert source.request_strategy.verify_tls and source.max_pages == 80


def test_namyangju_uses_explicit_registration_metadata_not_body_signature() -> None:
    source, case = SETTINGS.sources["namyangju"], CASES["namyangju"]
    assert "등록일" in source.html_profile.detail_date_selector
    actual = parse_profiled_html(
        case["list_html"], list_url=source.list_url, profile=source.html_profile,
        detail_loader=Mock(return_value=case["detail_html"] + "<p>본문 작성 2000-01-01</p>"),
    )
    assert str(actual[0].published_date) == case["date"]


def test_fixtures_do_not_contain_contact_details_or_scripts() -> None:
    for case in CASES.values():
        for key in ("list_html", "detail_html"):
            soup = BeautifulSoup(case[key], "html5lib")
            assert not soup.select("script,style,input,iframe")
            assert not soup.find_all(string=lambda n: isinstance(n, Comment))
            assert not re.search(r"[\w.+-]+@[\w.-]+|\b0\d{1,2}-\d{3,4}-\d{4}\b", soup.get_text())
            assert not any(x in soup.get_text() for x in ("담당자", "연락처", "전화번호"))
