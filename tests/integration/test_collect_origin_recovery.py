from __future__ import annotations

import json
import sqlite3
from contextlib import nullcontext
from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse
from zipfile import ZipFile

import pytest
import requests
from click.testing import CliRunner

from judgefinder.adapters.origin_discovery import HIBRAIN_LIST
from judgefinder.application.use_cases import CollectNoticesUseCase
from judgefinder.infrastructure.http.client import HttpResponse, RequestsHttpClient
from judgefinder.interfaces.cli.main import app

DAY = date(2026, 11, 3)
URL = "https://city.go.kr/view?board=A&id=12&mode=view"
DETAIL = ('<h1>제안서 평가위원 모집 공고</h1><time>2026-11-03</time>'
          '<article>평가위원 공개 모집 안내</article>')


def config_file(tmp_path: Path, *, hibrain: bool = False) -> Path:
    (tmp_path / "candidates.json").write_text(json.dumps([
        {"discovery_url": "https://www.hibrain.net/recruits/1", "origin_url": URL + "&page=9",
         "discovered_date": DAY.isoformat()},
        {"discovery_url": "https://www.hibrain.net/recruits/2", "origin_url": URL,
         "discovered_date": DAY.isoformat()},
    ]), encoding="utf-8")
    config = tmp_path / "settings.toml"
    config.write_text(f'''timezone="Asia/Seoul"
db_path="notices.db"
enabled_sources=["city"]
[origin_recovery]
enabled=true
hibrain={str(hibrain).lower()}
candidate_file="candidates.json"
throttle_seconds=0
[sources.city]
municipality="도시"
source_type="html"
list_url="https://city.go.kr/list?board=A"
engine_type="generic_egov_bbs"
[sources.city.html_profile]
container_selector="table"
row_selector="tr"
link_selector="a"
date_selector="td.date"
id_pattern="id=([1-9][0-9]*)"
detail_url_template="/view?board=A&id={{id}}&mode=view"
detail_title_selector="h1"
detail_date_selector="time"
detail_body_selector="article"
''', encoding="utf-8")
    return config


def run(config: Path, *args: str) -> str:
    result = CliRunner().invoke(app, ["--config-path", str(config), *args])
    assert result.exit_code == 0, (result.output, result.exception)
    return result.stdout


def records(config: Path) -> list[dict]:  # type: ignore[type-arg]
    output = run(config, "review-origins", "--status", "all")
    return [json.loads(line) for line in output.splitlines()]


def test_cli_official_first_recovery_deduplication_and_offline_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = config_file(tmp_path, hibrain=True)
    events: list[str] = []
    monkeypatch.setattr(CollectNoticesUseCase, "execute", lambda self, day: events.append("primary")
                        or [])
    def response(self: RequestsHttpClient, url: str, **kwargs: object) -> HttpResponse:
        if url == HIBRAIN_LIST:
            assert events == ["primary", "primary"]
            events.append("discovery")
            return HttpResponse(403, "denied", {}, url)
        assert url == URL
        events.append("detail")
        return HttpResponse(200, DETAIL, {}, url)
    monkeypatch.setattr(RequestsHttpClient, "get_response", response)
    assert run(config, "collect", "--date", "2026-11-03", "--days", "2").splitlines() == [URL]
    assert events == ["primary", "primary", "discovery", "detail"]
    monkeypatch.setattr(
        RequestsHttpClient, "get_response", Mock(side_effect=AssertionError("HTTP")),
    )
    rows = records(config)
    assert sorted(r["status"] for r in rows) == ["collected", "duplicate", "review_hold"]
    assert "403" in next(r["reason"] for r in rows if r["status"] == "review_hold")
    assert run(config, "list", "--date", "2026-11-03").splitlines() == [URL]
    # Rediscovery is optional: persisted verified records are not fetched again.
    config.write_text(config.read_text(encoding="utf-8").replace("hibrain=true", "hibrain=false"),
                      encoding="utf-8")
    assert run(config, "collect", "--date", "2026-11-03") == ""
    with sqlite3.connect(tmp_path / "notices.db") as conn:
        assert conn.execute("select count(*) from notices").fetchone() == (1,)
        assert conn.execute("select count(*) from notice_origin_identities").fetchone() == (1,)


@pytest.mark.parametrize("payload,status", [
    (DETAIL.replace("2026-11-03", "2026-11-02"), "outside_window"),
    (DETAIL.replace("<article>", "<aside>"), "review_hold"),
    (DETAIL.replace("평가위원 모집 공고", "평가위원회 평가 결과 공개"), "review_hold"),
])
def test_failed_or_outside_candidates_retained_and_hold_is_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str, status: str,
) -> None:
    config = config_file(tmp_path)
    monkeypatch.setattr(CollectNoticesUseCase, "execute", lambda self, day: [])
    client = Mock(return_value=HttpResponse(200, payload, {}, URL))
    monkeypatch.setattr(RequestsHttpClient, "get_response", client)
    assert run(config, "collect", "--date", DAY.isoformat()) == ""
    assert {r["status"] for r in records(config)} == {status}
    if status == "review_hold":
        client.return_value = HttpResponse(200, DETAIL, {}, URL)
        assert run(config, "collect", "--date", DAY.isoformat()).splitlines() == [URL]
        assert {r["attempts"] for r in records(config)} == {2}


def test_existing_database_migrates_without_losing_primary_url_variant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from judgefinder.infrastructure.db.models import NoticeModel
    from judgefinder.infrastructure.db.session import create_sqlite_engine
    config = config_file(tmp_path)
    engine = create_sqlite_engine(tmp_path / "notices.db")
    NoticeModel.__table__.create(engine)
    original = "https://city.go.kr/view?id=12&board=A&page=7"
    with sqlite3.connect(tmp_path / "notices.db") as conn:
        conn.execute("insert into notices values (1,?,?,?,?,?,?)", (
            "도시", "제안서 평가위원 모집 공고", original, "2026-11-03",
            "2026-11-03 01:00:00", "html",
        ))
    monkeypatch.setattr(CollectNoticesUseCase, "execute", lambda self, day: [])
    monkeypatch.setattr(
        RequestsHttpClient, "get_response", Mock(side_effect=AssertionError("HTTP")),
    )
    assert run(config, "collect", "--date", DAY.isoformat()) == ""
    assert {r["status"] for r in records(config)} == {"duplicate"}
    assert run(config, "list", "--date", DAY.isoformat()).splitlines() == [original]


def test_wider_window_can_recover_previously_outside_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = config_file(tmp_path)
    monkeypatch.setattr(CollectNoticesUseCase, "execute", lambda self, day: [])
    monkeypatch.setattr(RequestsHttpClient, "get_response", Mock(return_value=HttpResponse(
        200, DETAIL.replace("2026-11-03", "2026-11-02"), {}, URL,
    )))
    assert run(config, "collect", "--date", DAY.isoformat()) == ""
    assert {r["status"] for r in records(config)} == {"outside_window"}
    assert run(config, "collect", "--date", DAY.isoformat(), "--days", "2").splitlines() == [URL]


def test_cli_committee_search_collects_verified_notices_and_retains_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = config_file(tmp_path)
    text = config.read_text(encoding="utf-8").replace(
        'candidate_file="candidates.json"', "committee_search=true",
    )
    text += 'search_param="q"\n'
    config.write_text(text, encoding="utf-8")

    titles = {
        12: "제안서 평가위원(심의위원) 모집",
        13: "사업 선정심의위원 후보자 모집",
        14: "정책 심의위원 후보자 모집",
        15: "사업 심의위원 후보자 모집",
        16: "시설 심의위원 후보자 모집",
        17: "평가위원(심의위원) 후보자 모집",
        18: "공지사항 확인 안내",
        19: "제안서 심의위원 심의 결과 공개",
        20: "「여수시 콜센터 민간위탁 운영」 제안서 심의위원 모집 공고",
        21: "「교통정보시스템 구축」 기술제안서 심사위원 후보자 등록 공고",
        22: "농산물 물류시스템 구축 민간위탁 수탁자 선정심사위원 모집 공고",
        23: "「공공건축 설계용역」 심사위원 모집 공고",
        24: "주민참여예산 제안사업 심사위원 모집 공고",
        25: "제안서 심사위원 명단 공개",
    }
    bodies = {
        12: "제안서 평가위원 후보자 모집",
        13: "제안서 평가 위원 후보자 모집",
        14: "정책위원회를 구성합니다<nav>다른 글 평가위원 모집</nav>",
        15: '<img alt="공고문" src="notice.png">',
        17: '<img alt="공고문" src="notice.png">',
        19: "제안서 평가위원 명단과 점수를 공개합니다.",
        20: "수탁기관을 선정하기 위한 제안서 심의위원(후보자)을 다음과 같이 공개 모집합니다.",
        21: "시스템 구축 제안서의 기술능력을 심사합니다.",
        22: '「농산물 물류시스템 구축」 수탁자 선정을 위한 위원 모집 '
            '<a href="https://other.go.kr/form.hwpx">양식.hwpx</a>'
            '<a href="/form.hwpx">신청서.hwpx</a>',
        23: '별도 사업 「농산물 물류시스템 구축」을 참고하세요. '
            '<a href="/form.hwpx">공고문.hwpx</a>',
        24: "모집분야: 주민참여, 접수기간: 11월 10일까지, 접수방법: 이메일",
        25: "제안서 심사위원 모집을 통해 구성한 위원 명단입니다.",
    }
    calls: list[tuple[str, int | str]] = []

    def response(self: RequestsHttpClient, url: str, **kwargs: object) -> HttpResponse:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if parsed.path == "/list":
            assert query["board"] == ["A"]
            keyword = query["q"][0]
            by_keyword = {
                "평가위원": [12], "심의위원": list(range(12, 21)),
                "심사위원": list(range(21, 26)),
            }
            calls.append(("list", keyword))
            ids = by_keyword[keyword] if query["pageIndex"] == ["1"] else []
            listing_titles = {**titles, 13: "사업 선정…"}
            rows = "".join(
                f'<tr><td><a href="/view?id={i}">{listing_titles[i]}</a></td>'
                f'<td class="date">{DAY}</td></tr>' for i in ids
            )
            return HttpResponse(200, f"<table>{rows}</table>", {}, url)

        notice_id = int(query["id"][0])
        calls.append(("detail", notice_id))
        if notice_id == 16:
            return HttpResponse(404, "", {}, url)
        payload = (
            f"<h1>{titles[notice_id]}</h1><time>{DAY}</time>"
            f"<article>{bodies[notice_id]}</article>"
        )
        return HttpResponse(200, payload, {}, url)

    def get_text(self: RequestsHttpClient, url: str, **kwargs: object) -> str:
        result = response(self, url, **kwargs)
        assert result.ok
        return result.text

    monkeypatch.setattr(RequestsHttpClient, "get_text", get_text)
    monkeypatch.setattr(RequestsHttpClient, "get_response", response)

    archive = BytesIO()
    with ZipFile(archive, "w") as document:
        document.writestr(
            "Contents/section0.xml",
            '<hp:p xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
            '<hp:t>본인은 농산물 물류시스템 구축 수탁자 선정의 사업설명서 '
            '심사위원으로 위촉받아 평가업무를 수행합니다.</hp:t></hp:p>',
        )
    attachment = Mock(status_code=200)
    attachment.iter_content.return_value = [archive.getvalue()]
    download = Mock(return_value=nullcontext(attachment))
    monkeypatch.setattr(requests, "get", download)

    expected = {URL.replace("id=12", f"id={i}") for i in (12, 13, 17, 20, 21, 22)}
    assert set(run(config, "collect", "--date", DAY.isoformat()).splitlines()) == expected
    assert calls.index(("detail", 12)) < calls.index(("list", "심의위원"))
    assert calls.count(("detail", 12)) == 1
    assert ("list", "심사위원") in calls
    assert [call.args[0] for call in download.call_args_list] == [
        "https://city.go.kr/form.hwpx", "https://city.go.kr/form.hwpx",
    ]
    assert all(call.kwargs["allow_redirects"] is False for call in download.call_args_list)

    results = {int(row["official_id"]): row for row in records(config)}
    assert {k: row["status"] for k, row in results.items()} == {
        12: "duplicate", 13: "collected", 14: "review_hold",
        15: "review_hold", 16: "review_hold", 17: "collected", 19: "review_hold",
        20: "collected", 21: "collected", 22: "collected",
        23: "review_hold", 24: "review_hold", 25: "review_hold",
    }
    assert ("detail", 18) not in calls
    assert "평가위원" not in results[14]["body_text"]
    assert results[15]["reason"] == "Official notice body is empty"
    assert "404" in results[16]["reason"]
    assert results[19]["reason"] == results[25]["reason"] == (
        "Official notice is a result announcement"
    )

    run(config, "collect", "--date", DAY.isoformat())
    assert len(records(config)) == 13
    assert calls.count(("detail", 13)) == 1
    assert calls.count(("detail", 15)) == 2
    config.write_text(text.replace("committee_search=true", "committee_search=false"),
                      encoding="utf-8")
    calls.clear()
    assert run(config, "collect", "--date", DAY.isoformat()).splitlines() == [URL]
    assert all(call[1] not in {"심의위원", "심사위원", 14, 15, 16, 19, 23, 24, 25}
               for call in calls)
    assert set(run(config, "list", "--date", DAY.isoformat()).splitlines()) == expected
    with sqlite3.connect(tmp_path / "notices.db") as conn:
        assert conn.execute("select count(*) from notices").fetchone() == (6,)


def test_okcheon_captured_notice_collects_only_with_verified_attachment_and_browser_headers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).parents[2]
    case = json.loads((root / "tests/fixtures/hibrain_20261118_committee.json").read_text("utf-8"))
    text = (root / case["config_path"]).read_text("utf-8")
    config = tmp_path / "okcheon.toml"
    config.write_text("\n".join(
        'db_path="notices.db"' if line.startswith("db_path =") else line
        for line in text.splitlines()
    ), encoding="utf-8")
    calls: list[str] = []

    def response(self: RequestsHttpClient, url: str, **kwargs: object) -> HttpResponse:
        assert "Chrome/" in kwargs["headers"]["User-Agent"]
        query = parse_qs(urlparse(url).query)
        calls.append(url)
        if "selectBbsNttView" in url:
            return HttpResponse(200, case["detail_html"], {}, url)
        assert query["bbsNo"] == ["40"]
        keyword = query["searchKrwd"][0]
        assert keyword in {"평가위원", "심의위원", "심사위원"}
        listing = (case["list_html"] if keyword == "심의위원" and query["pageIndex"] == ["1"]
                   else '<table class="p-table simple"><tbody></tbody></table>')
        return HttpResponse(200, listing, {}, url)

    monkeypatch.setattr(RequestsHttpClient, "get_response", response)
    monkeypatch.setattr(
        RequestsHttpClient, "get_text", lambda self, url, **kwargs: response(self, url, **kwargs).text,
    )
    archive = BytesIO()
    with ZipFile(archive, "w") as document:
        document.writestr(
            "Contents/section0.xml",
            '<hp:p xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
            f'<hp:t>{case["attachment_text"]}</hp:t></hp:p>',
        )
    attachment = Mock(status_code=200)
    attachment.iter_content.return_value = [archive.getvalue()]

    def download(url: str, **kwargs: object) -> object:
        assert url == "https://www.oc.go.kr/www/downloadBbsFile.do?atchmnflNo=325627"
        assert "Chrome/" in kwargs["headers"]["User-Agent"]
        assert kwargs["headers"]["Referer"] == case["url"]
        assert kwargs["allow_redirects"] is False
        return nullcontext(attachment)

    monkeypatch.setattr(requests, "get", download)
    for attempt in range(2):
        expected_new = [case["url"]] if attempt == 0 else []
        assert run(config, "collect", "--date", case["date"]).splitlines() == expected_new
        assert run(config, "list", "--date", case["date"]).splitlines() == [case["url"]]
    assert {row["status"] for row in records(config)} == {"collected"}
    assert any(parse_qs(urlparse(url).query).get("searchKrwd") == ["심의위원"] for url in calls)
    with sqlite3.connect(tmp_path / "notices.db") as con:
        assert con.execute("select title,published_date,url from notices").fetchall() == [
            (case["title"], case["date"], case["url"]),
        ]
