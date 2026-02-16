from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from judgefinder.adapters.sources.sample_city.parser import parse_sample_city_notices
from judgefinder.domain.entities import Notice, SourceType
from judgefinder.infrastructure.http.client import HttpClient


@dataclass(slots=True)
class SampleCitySource:
    slug: str
    municipality: str
    source_type: SourceType
    list_url: str
    timezone: ZoneInfo
    http_client: HttpClient
    fixture_path: Path | None = None

    def fetch(self, target_date: date) -> list[Notice]:
        html = self._load_html()
        fetched_at = datetime.now(tz=self.timezone)
        return parse_sample_city_notices(
            html,
            municipality=self.municipality,
            list_url=self.list_url,
            target_date=target_date,
            fetched_at=fetched_at,
            source_type=self.source_type,
        )

    def _load_html(self) -> str:
        if self.fixture_path is not None:
            return self.fixture_path.read_text(encoding="utf-8")
        return self.http_client.get_text(self.list_url)
