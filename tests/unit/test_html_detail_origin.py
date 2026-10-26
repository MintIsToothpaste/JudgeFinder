from dataclasses import replace
from datetime import date

import pytest

from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.domain.source_profiles import HtmlProfile

PROFILE = HtmlProfile(
    container_selector="table", row_selector="tbody tr", date_selector="td.date",
    link_attribute="onclick", link_selector="td.subject",
    id_pattern="searchDetail[(]'([1-9][0-9]*)'",
    detail_url_template="https://www.example.org/notice?id={id}",
    detail_title_selector="h2", detail_origin="https://www.example.org",
)
HTML = (
    '<table><tbody><tr><td class="subject" onclick="searchDetail(\'42274\')">'
    '제안서 평가...</td><td class="date">2026-09-08</td></tr></tbody></table>'
)


def test_explicit_public_detail_origin_preserves_listing_registration_date() -> None:
    urls = []

    def load(url: str) -> str:
        urls.append(url)
        return "<h2>제안서 평가위원 후보자 공개모집 공고</h2><p>게시기간 2026-09-01</p>"

    notice = parse_profiled_html(
        HTML, list_url="https://archive.example.org/list", profile=PROFILE,
        detail_loader=load,
    )[0]
    assert notice.title == "제안서 평가위원 후보자 공개모집 공고"
    assert notice.published_date == date(2026, 9, 8)
    assert urls == ["https://www.example.org/notice?id=42274"]


def test_cross_host_details_still_fail_without_explicit_origin() -> None:
    with pytest.raises(ValueError, match="configured host"):
        parse_profiled_html(
            HTML, list_url="https://archive.example.org/list",
            profile=replace(PROFILE, detail_origin=""),
        )


@pytest.mark.parametrize("origin", [
    "http://www.example.org", "//www.example.org", "https://other.example.org",
    "https://www.example.org/", "https://www.example.org/path",
    "https://www.example.org?next=x", "https://www.example.org#fragment",
    "https://user:pass@www.example.org", "https://www.example.org:443",
    "https://www.example.org;params", "https://", "https://{id}.example.org",
])
def test_invalid_or_unmatched_origin_is_rejected(origin: str) -> None:
    with pytest.raises(ValueError, match="detail_origin"):
        replace(PROFILE, detail_origin=origin)


@pytest.mark.parametrize("template", [
    "/notice?id={id}", "https://other.example.org/notice?id={id}",
    "http://www.example.org/notice?id={id}",
    "https://user:pass@www.example.org/notice?id={id}",
    "https://www.example.org.evil.test/notice?id={id}",
])
def test_unpinned_template_cannot_use_origin(template: str) -> None:
    with pytest.raises(ValueError, match="detail_origin"):
        replace(PROFILE, detail_url_template=template)


def test_origin_requires_validated_identifier_mapping() -> None:
    with pytest.raises(ValueError, match="detail_origin"):
        replace(PROFILE, link_attribute="href", id_pattern="", detail_url_template="")


def test_invalid_identifier_is_not_sent_to_detail_host() -> None:
    with pytest.raises(ValueError, match="identifier"):
        parse_profiled_html(
            HTML.replace("42274", "0"), list_url="https://archive.example.org/list",
            profile=PROFILE,
        )
