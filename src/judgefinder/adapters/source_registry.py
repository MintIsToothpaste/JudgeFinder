from __future__ import annotations

from zoneinfo import ZoneInfo

from judgefinder.adapters.config import AppConfig
from judgefinder.adapters.sources.municipal_rss.source import MunicipalRssSource
from judgefinder.adapters.sources.pocheon_eminwon.source import PocheonEminwonSource
from judgefinder.adapters.sources.sample_city.source import SampleCitySource
from judgefinder.adapters.sources.seongbuk.source import SeongbukSource
from judgefinder.domain.ports import NoticeSource
from judgefinder.infrastructure.http.client import HttpClient

MUNICIPAL_RSS_SLUGS: set[str] = {
    "hanam",
    "cheorwon",
    "jecheon",
    "okcheon",
}


class SourceRegistry:
    def __init__(self, config: AppConfig, http_client: HttpClient, timezone: ZoneInfo) -> None:
        self._config = config
        self._http_client = http_client
        self._timezone = timezone

    def build_enabled_sources(self) -> list[NoticeSource]:
        sources: list[NoticeSource] = []
        for slug in self._config.enabled_sources:
            source_config = self._config.sources.get(slug)
            if source_config is None:
                raise ValueError(f"Source '{slug}' is enabled but not configured.")

            if slug == "sample_city":
                sources.append(
                    SampleCitySource(
                        slug=source_config.slug,
                        municipality=source_config.municipality,
                        source_type=source_config.source_type,
                        list_url=source_config.list_url,
                        fixture_path=source_config.fixture_path,
                        timezone=self._timezone,
                        http_client=self._http_client,
                    )
                )
                continue

            if slug == "seongbuk":
                sources.append(
                    SeongbukSource(
                        slug=source_config.slug,
                        municipality=source_config.municipality,
                        source_type=source_config.source_type,
                        list_url=source_config.list_url,
                        fixture_path=source_config.fixture_path,
                        timezone=self._timezone,
                        http_client=self._http_client,
                    )
                )
                continue

            if slug == "pocheon":
                sources.append(
                    PocheonEminwonSource(
                        slug=source_config.slug,
                        municipality=source_config.municipality,
                        source_type=source_config.source_type,
                        list_url=source_config.list_url,
                        fixture_path=source_config.fixture_path,
                        timezone=self._timezone,
                        http_client=self._http_client,
                    )
                )
                continue

            if slug in MUNICIPAL_RSS_SLUGS:
                sources.append(
                    MunicipalRssSource(
                        slug=source_config.slug,
                        municipality=source_config.municipality,
                        source_type=source_config.source_type,
                        list_url=source_config.list_url,
                        fixture_path=source_config.fixture_path,
                        timezone=self._timezone,
                        http_client=self._http_client,
                    )
                )
                continue

            raise ValueError(f"Unknown source slug: {slug}")

        return sources

    def list_enabled_source_slugs(self) -> list[str]:
        return list(self._config.enabled_sources)
