from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

DATE_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


@dataclass(slots=True)
class PocheonEminwonRow:
    title: str
    url: str
    published_date: date
    searchable_text: str


def extract_pocheon_eminwon_rows(
    page_html: str, *, list_url: str
) -> list[PocheonEminwonRow]:
    parser = _PocheonEminwonListParser(list_url=list_url)
    parser.feed(page_html)
    parser.close()
    return parser.rows


class _PocheonEminwonListParser(HTMLParser):
    def __init__(self, *, list_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self._list_url = list_url
        self.rows: list[PocheonEminwonRow] = []

        self._in_script = False
        self._in_style = False
        self._in_tr = False
        self._in_td = False
        self._in_notice_anchor = False

        self._row_cells: list[str] = []
        self._row_href = ""
        self._row_title = ""
        self._current_cell_parts: list[str] = []
        self._current_anchor_text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            self._in_script = True
            return
        if tag == "style":
            self._in_style = True
            return
        if self._in_script or self._in_style:
            return

        if tag == "tr":
            self._in_tr = True
            self._row_cells = []
            self._row_href = ""
            self._row_title = ""
            return

        if not self._in_tr:
            return

        if tag == "td":
            self._in_td = True
            self._current_cell_parts = []
            return

        if tag == "br" and self._in_td:
            self._current_cell_parts.append(" ")
            return

        if tag == "a":
            href = dict(attrs).get("href", "") or ""
            if "selectEminwonView.do" in href:
                self._in_notice_anchor = True
                self._row_href = href
                self._current_anchor_text_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script = False
            return
        if tag == "style":
            self._in_style = False
            return
        if self._in_script or self._in_style:
            return

        if not self._in_tr:
            return

        if tag == "a" and self._in_notice_anchor:
            anchor_text = _normalize_whitespace("".join(self._current_anchor_text_parts))
            if anchor_text:
                self._row_title = anchor_text
            self._in_notice_anchor = False
            return

        if tag == "td" and self._in_td:
            cell_text = _normalize_whitespace("".join(self._current_cell_parts))
            self._row_cells.append(cell_text)
            self._in_td = False
            return

        if tag == "tr":
            self._flush_row()
            self._in_tr = False

    def handle_data(self, data: str) -> None:
        if self._in_script or self._in_style:
            return
        if self._in_td:
            self._current_cell_parts.append(data)
        if self._in_notice_anchor:
            self._current_anchor_text_parts.append(data)

    def _flush_row(self) -> None:
        if not self._row_href or not self._row_title:
            return
        row_text = _normalize_whitespace(" ".join(self._row_cells))
        date_match = DATE_PATTERN.search(row_text)
        if date_match is None:
            return
        try:
            published_date = date.fromisoformat(date_match.group(1))
        except ValueError:
            return

        notice_url = _normalize_eminwon_notice_url(urljoin(self._list_url, self._row_href))
        searchable_text = _normalize_whitespace(f"{self._row_title} {row_text}")
        self.rows.append(
            PocheonEminwonRow(
                title=self._row_title,
                url=notice_url,
                published_date=published_date,
                searchable_text=searchable_text,
            )
        )


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def _normalize_eminwon_notice_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.path != "/www/selectEminwonView.do":
        return url

    query_params = parse_qs(parsed.query, keep_blank_values=True)
    key = query_params.get("key", [""])[0]
    notice_no = query_params.get("notAncmtMgtNo", [""])[0]
    notice_type = query_params.get("notAncmtSeCode", [""])[0]
    if not key or not notice_no:
        return url

    normalized_query: dict[str, str] = {
        "key": key,
        "notAncmtMgtNo": notice_no,
    }
    if notice_type:
        normalized_query["notAncmtSeCode"] = notice_type

    return urlunparse(parsed._replace(query=urlencode(normalized_query)))
