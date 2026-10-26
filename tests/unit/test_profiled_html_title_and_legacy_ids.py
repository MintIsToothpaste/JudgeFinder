from __future__ import annotations

from dataclasses import replace
from datetime import date
from unittest.mock import Mock

import pytest
from bs4 import BeautifulSoup

from judgefinder.adapters.sources.generic_engine.profiled_html import (
    _title_text,
    parse_profiled_html,
)
from judgefinder.domain.source_profiles import HtmlProfile

PROFILE = HtmlProfile(
    container_selector="table", row_selector="tbody tr", date_selector="td.date",
    id_pattern=r"id=([1-9][0-9]*)(?:&|$)", detail_url_template="/view?id={id}",
)
HTML = (
    '<table><tbody><tr><td><a href="/view?id=123">평가위원 모집'
    '<span class="badge">결과</span></a></td>'
    '<td class="date">2026-09-21</td></tr></tbody></table>'
)


def test_title_badge_exclusion_is_opt_in_and_does_not_mutate_the_node() -> None:
    soup = BeautifulSoup('<h1><span class="badge">고시공고</span>평가<b>위원</b> 모집</h1>',
        "html.parser")
    node = soup.find("h1")
    assert node is not None
    assert _title_text(node, ".badge") == "평가위원 모집"
    assert _title_text(node, "") == "고시공고평가위원 모집"
    assert node.find("span", class_="badge") is not None


def test_default_title_extraction_preserves_existing_behavior() -> None:
    notice = parse_profiled_html(HTML, list_url="https://example.org/list", profile=PROFILE)[0]
    assert notice.title == "평가위원 모집결과"


def test_excluded_listing_badge_cannot_make_recruitment_skip_its_detail() -> None:
    profile = replace(PROFILE, title_exclude_selector=".badge",
        detail_title_selector="h1", detail_date_selector="time")
    loader = Mock(return_value=(
        '<h1><span class="badge">고시공고</span>평가위원 모집</h1>'
        '<time>2026-09-21</time>'
    ))
    notices = parse_profiled_html(HTML, list_url="https://example.org/list", profile=profile,
        detail_loader=loader, recruitment_only=True)
    assert notices[0].title == "평가위원 모집"
    loader.assert_called_once_with("https://example.org/view?id=123")


def test_only_out_of_window_unsupported_identifier_is_skipped() -> None:
    old = HTML.replace("id=123", "id=01_8723").replace("2026-09-21", "2015-12-29")
    mixed = old.replace("</tbody>", HTML.split("<tbody>")[1])
    actual = parse_profiled_html(mixed, list_url="https://example.org/list", profile=PROFILE,
        detail_not_before=date(2025, 10, 5))
    assert len(actual) == 1 and actual[0].url == "https://example.org/view?id=123"


@pytest.mark.parametrize("published", ["2025-10-05", "2026-09-21", "2026-12-01", "invalid"])
def test_current_or_undated_unsupported_identifier_still_fails(published: str) -> None:
    payload = HTML.replace("id=123", "id=01_8723").replace("2026-09-21", published)
    with pytest.raises(ValueError, match="unsupported notice identifier"):
        parse_profiled_html(payload, list_url="https://example.org/list", profile=PROFILE,
            detail_not_before=date(2025, 10, 5))


def test_without_date_boundary_legacy_identifier_is_not_silently_ignored() -> None:
    payload = HTML.replace("id=123", "id=01_8723").replace("2026-09-21", "2015-12-29")
    with pytest.raises(ValueError, match="unsupported notice identifier"):
        parse_profiled_html(payload, list_url="https://example.org/list", profile=PROFILE)
