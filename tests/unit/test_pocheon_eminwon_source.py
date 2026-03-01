from __future__ import annotations

from judgefinder.adapters.sources.pocheon_eminwon.source import (
    DEFAULT_POCHEON_EMINWON_LIST_URL,
    _resolve_pocheon_list_url,
)


def test_resolve_pocheon_list_url_rewrites_legacy_rss_url() -> None:
    resolved = _resolve_pocheon_list_url(
        "https://www.pocheon.go.kr/rssBbsNtt.do?bbsNo=19"
    )
    assert resolved == DEFAULT_POCHEON_EMINWON_LIST_URL


def test_resolve_pocheon_list_url_keeps_eminwon_url() -> None:
    list_url = "https://www.pocheon.go.kr/www/selectEminwonList.do?key=12563&notAncmtSeCode=01"
    resolved = _resolve_pocheon_list_url(list_url)
    assert resolved == list_url
