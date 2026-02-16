from __future__ import annotations

from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from judgefinder.domain.entities import Notice, SourceType


def parse_sample_city_notices(
    html: str,
    *,
    municipality: str,
    list_url: str,
    target_date: date,
    fetched_at: datetime,
    source_type: SourceType,
) -> list[Notice]:
    soup = BeautifulSoup(html, "html.parser")
    notices: list[Notice] = []

    for item in soup.select("#notices .notice-item"):
        link = item.select_one("a")
        date_node = item.select_one(".date")
        if link is None or date_node is None:
            continue

        href_value = link.get("href")
        if not isinstance(href_value, str) or not href_value:
            continue
        href = href_value

        try:
            published_date = date.fromisoformat(date_node.get_text(strip=True))
        except ValueError:
            continue

        if published_date != target_date:
            continue

        title = link.get_text(strip=True)
        notices.append(
            Notice(
                id=None,
                municipality=municipality,
                title=title,
                url=urljoin(list_url, href),
                published_date=published_date,
                fetched_at=fetched_at,
                source_type=source_type,
            )
        )

    return notices
