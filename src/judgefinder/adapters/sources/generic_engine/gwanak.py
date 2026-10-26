from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup, Tag

BOARD_PATHS = {
    "gosi": "/site/gwanak/ex/bbsNew/",
    "news": "/site/gwanak/ex/bbs/",
}
VIEW_CALL = re.compile(
    r"(?:javascript:\s*)?doBbsFView\(([^()]*)\)\s*;?\s*(?:return\s+false\s*;?)?"
)
NUMERIC_ARGUMENT = re.compile(r"(?:'([1-9][0-9]*)'|\"([1-9][0-9]*)\"|([1-9][0-9]*))")


def gwanak_board_kind(url: str, *, detail: bool = False) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"}:
        return None
    if parsed.hostname not in {"www.gwanak.go.kr", "gwanak.go.kr"}:
        return None
    suffix = "View.do" if detail else "List.do"
    return next((kind for kind, path in BOARD_PATHS.items() if parsed.path == path + suffix), None)


def build_gwanak_detail_url(anchor: Tag, *, list_url: str) -> str:
    kind = gwanak_board_kind(list_url)
    source = anchor.get("onclick") or anchor.get("href")
    if kind is None or not isinstance(source, str):
        return ""
    call = VIEW_CALL.fullmatch(source.strip())
    if call is None:
        return ""
    arguments: list[str] = []
    for value in call.group(1).split(","):
        match = NUMERIC_ARGUMENT.fullmatch(value.strip())
        if match is None:
            return ""
        arguments.append(next(group for group in match.groups() if group is not None))

    parsed = urlparse(list_url)
    list_query = parse_qs(parsed.query, keep_blank_values=True)
    if kind == "gosi" and len(arguments) == 1 and list_query.get("typeCode") == ["1"]:
        query = {"not_ancmt_mgt_no": arguments[0], "typeCode": "1"}
    elif kind == "news" and len(arguments) == 4 and list_query.get("cbIdx") == [arguments[0]]:
        query = {"cbIdx": arguments[0], "bcIdx": arguments[1], "parentSeq": arguments[3]}
    else:
        return ""
    return urlunparse(parsed._replace(
        path=BOARD_PATHS[kind] + "View.do", query=urlencode(query), params="", fragment="",
    ))


def gwanak_registration_text(anchor: Tag, *, detail_url: str) -> str:
    kind = gwanak_board_kind(detail_url, detail=True)
    row = anchor.find_parent("tr")
    table = anchor.find_parent("table")
    if kind is None or row is None or table is None:
        return ""
    headers = [th.get_text(strip=True) for th in table.select("thead th")]
    label = "등록일" if kind == "gosi" else "작성일"
    # The live gosi HTML omits a </td>; later cells become children of the title cell.
    cells = [td for td in row.find_all("td")
             if td.find_parent("tr") is row and td.find_parent("table") is table]
    if headers.count(label) != 1 or len(cells) != len(headers):
        return ""
    value = cells[headers.index(label)].get_text(strip=True)
    if not re.fullmatch(r"(?:[0-9]{8}|[0-9]{4}[./-][0-9]{2}[./-][0-9]{2})", value):
        return ""
    return value


def gwanak_listing_row_count(payload: str) -> int:
    soup = BeautifulSoup(payload, "html.parser")
    table = soup.select_one("#boardDivId table.list")
    if table is None or table.select_one("thead") is None or table.select_one("tbody") is None:
        raise ValueError("unexpected Gwanak listing structure; absence of notices is unverified")
    rows = [row for row in table.select("tbody tr") if row.find_parent("table") is table]
    notice_rows = [row for row in rows if row.select_one("td.title") is not None]
    if notice_rows:
        return len(notice_rows)
    empty_text = table.get_text(" ", strip=True)
    if not rows or re.search(r"(?:게시물|자료|데이터|검색\s*결과).*없", empty_text):
        return 0
    raise ValueError("unrecognized Gwanak listing rows; absence of notices is unverified")
