from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs

import pytest
from click.testing import CliRunner

from judgefinder.adapters.config import load_config
from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.infrastructure.http.client import RequestsHttpClient
from judgefinder.interfaces.cli.main import app

ROOT = Path(__file__).parents[2]
TITLE = (
    "「2026년 안동원도심상권 해외선진지 견학 및 벤치마킹 용역」"
    "제안서 평가위원(후보자) 모집 공고"
)
URL = "https://www.andong.go.kr/portal/bbs/view.do?bIdx=781354&ptIdx=76&mId=0401070000"
LIST = f"""<p class="page_num">현재 페이지 <span>1</span> / 전체 페이지 1</p>
<table class="bod_list"><tbody><tr>
<td class="list_tit"><a href="#" data-action="/portal/bbs/view.do?bIdx=781354&amp;ptIdx=76">
{TITLE}</a></td><td class="list_date">2026-09-23</td></tr></tbody></table>"""
DETAIL = f"""<div class="bod_view"><h4>{TITLE}</h4><div class="view_info"><ul>
<li class="view_date"><span>작성일</span> : 2026-09-23</li></ul></div>
<div class="view_cont">공정하고 투명한 제안서 평가를 위한 평가위원을 다음과 같이 공개 모집합니다.
</div></div>"""


def test_related_board_collects_real_date_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    example = ROOT / "config/batch-hibrain-recovery.example.toml"
    config = tmp_path / "config.toml"
    db = tmp_path / "notices.db"
    text = re.sub(r'^db_path = .+$', f'db_path = "{db.as_posix()}"',
                  example.read_text(encoding="utf-8"), flags=re.MULTILINE)
    text = re.sub(r'^enabled_sources = .+$', 'enabled_sources = ["andong_related"]',
                  text, flags=re.MULTILINE)
    config.write_text(text.replace("throttle_seconds = 0.3", "throttle_seconds = 0.0"),
                      encoding="utf-8")
    calls: list[str] = []

    def post_text(
        self: RequestsHttpClient, url: str, *, data: bytes,
        timeout_seconds: float = 10.0, headers: Mapping[str, str] | None = None,
        use_session: bool = False, verify_tls: bool = True,
    ) -> str:
        assert url == "https://www.andong.go.kr/portal/bbs/list.do"
        assert use_session and verify_tls and headers and "Referer" in headers
        query = parse_qs(data.decode("ascii"))
        assert query["ptIdx"] == ["76"] and query["searchType"] == ["b_title"]
        assert query["searchTxt"] == ["평가위원"]
        calls.append(url)
        if query["page"] != ["1"]:
            return (
                '<table class="bod_list"><tbody><tr><td>게시물이 없습니다.</td>'
                '</tr></tbody></table>'
            )
        return LIST

    def get_text(
        self: RequestsHttpClient, url: str, timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None, use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        assert url == URL and use_session and verify_tls
        calls.append(url)
        return DETAIL

    monkeypatch.setattr(RequestsHttpClient, "post_text", post_text)
    monkeypatch.setattr(RequestsHttpClient, "get_text", get_text)
    runner = CliRunner()
    args = ["--config-path", str(config)]
    for _ in range(2):
        result = runner.invoke(app, [*args, "collect", "--date", "2026-10-29", "--days", "38"])
        assert result.exit_code == 0, result.output
        assert result.stdout.splitlines() == [URL]
    with sqlite3.connect(db) as connection:
        assert connection.execute(
            "select municipality,title,published_date,url from notices",
        ).fetchall() == [("안동시", TITLE, "2026-09-23", URL)]
    count = len(calls)
    listed = runner.invoke(app, [*args, "list", "--date", "2026-09-23"])
    assert listed.exit_code == 0 and listed.stdout.splitlines() == [URL]
    assert len(calls) == count


def test_sokcho_uses_observed_title_form_without_a_fixture() -> None:
    source = load_config(ROOT / "config/batch-cafe-20261028.example.toml").sources["sokcho"]
    assert source.fixture_path is None
    assert "searchCondition=TITLE" in source.list_url
    assert source.html_profile is not None and source.html_profile.request_method == "POST"


@pytest.mark.parametrize("replacement", ["", "2026-02-30"])
def test_related_board_never_substitutes_body_or_repost_date(replacement: str) -> None:
    source = load_config(ROOT / "config/batch-hibrain-recovery.example.toml").sources[
        "andong_related"
    ]
    assert source.html_profile is not None
    detail = DETAIL.replace("2026-09-23", replacement)
    detail += "<p>하이브레인 등록일 2026-09-30. 모집기간 2026-09-23 ~ 2026-10-01</p>"
    with pytest.raises(ValueError, match="invalid title or registration date"):
        parse_profiled_html(
            LIST, list_url=source.list_url, profile=source.html_profile,
            detail_loader=lambda _: detail, detail_not_before=date(2026, 9, 22),
        )

