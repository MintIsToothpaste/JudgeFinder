from __future__ import annotations

from datetime import date
from pathlib import Path

from judgefinder.adapters.sources.pocheon_eminwon.parser import (
    extract_pocheon_eminwon_rows,
)


def test_extract_pocheon_eminwon_rows_parses_relative_detail_links() -> None:
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "pocheon_eminwon_list.html"
    page_html = fixture_path.read_text(encoding="utf-8")

    rows = extract_pocheon_eminwon_rows(
        page_html,
        list_url="https://www.pocheon.go.kr/www/selectEminwonList.do?key=12563&notAncmtSeCode=01",
    )

    assert len(rows) == 3
    assert (
        rows[0].url
        == "https://www.pocheon.go.kr/www/selectEminwonView.do?key=12563&notAncmtMgtNo=64616&notAncmtSeCode=01"
    )
    assert rows[0].published_date == date(2026, 2, 2)


def test_extract_pocheon_eminwon_rows_collects_title_text() -> None:
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "pocheon_eminwon_list.html"
    page_html = fixture_path.read_text(encoding="utf-8")

    rows = extract_pocheon_eminwon_rows(
        page_html,
        list_url="https://www.pocheon.go.kr/www/selectEminwonList.do?key=12563&notAncmtSeCode=01",
    )

    assert "평가위원" in rows[0].title
    assert "도로명주소 고시" in rows[1].searchable_text
