from dataclasses import replace

import pytest

from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.domain.source_profiles import HtmlProfile

PROFILE = HtmlProfile(
    container_selector="table", row_selector="tr", date_selector="time",
    id_pattern=r"no=([^&]+)", detail_url_template="/view?no={id}", id_format="hex32",
)
IDENTIFIER = "0123456789abcdef0123456789ABCDEF"


def parse(identifier: str, profile: HtmlProfile = PROFILE):
    payload = (
        f'<table><tr><td><a href="/view?no={identifier}&amp;GotoPage=8">'
        '평가위원 모집</a><time>2026-10-02</time></td></tr></table>'
    )
    return parse_profiled_html(payload, list_url="https://example.org/list", profile=profile)


def test_explicit_hex_id_produces_pagination_independent_url():
    assert parse(IDENTIFIER)[0].url == f"https://example.org/view?no={IDENTIFIER}"


def test_default_numeric_format_remains_strict():
    with pytest.raises(ValueError, match="unsupported notice identifier"):
        parse(IDENTIFIER, replace(PROFILE, id_format="numeric"))


@pytest.mark.parametrize("identifier", ["123", "a" * 31, "a" * 33, "g" * 32, "../view", "%2f" * 16])
def test_hex_format_rejects_unvalidated_identifiers(identifier):
    with pytest.raises(ValueError, match="unsupported notice identifier"):
        parse(identifier)


def test_hex_format_does_not_weaken_origin_validation():
    with pytest.raises(ValueError, match="configured host"):
        parse(IDENTIFIER, replace(PROFILE, detail_url_template="https://other.org/?no={id}"))


@pytest.mark.parametrize("format", ["uuid", "", "anything"])
def test_unknown_format_is_rejected(format):
    with pytest.raises(ValueError, match="id_format"):
        replace(PROFILE, id_format=format)


def test_hex_format_requires_extraction_pattern():
    with pytest.raises(ValueError, match="identifier pattern"):
        replace(PROFILE, id_pattern="", detail_url_template="")
