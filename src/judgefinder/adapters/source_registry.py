from __future__ import annotations

from zoneinfo import ZoneInfo

from judgefinder.adapters.config import AppConfig, SourceConfig
from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.adapters.sources.municipal_rss.source import MunicipalRssSource
from judgefinder.adapters.sources.noop.source import NoopSource
from judgefinder.adapters.sources.pocheon_eminwon.source import PocheonEminwonSource
from judgefinder.adapters.sources.sample_city.source import SampleCitySource
from judgefinder.adapters.sources.seongbuk.source import SeongbukSource
from judgefinder.domain.ports import NoticeSource
from judgefinder.domain.source_profiles import AccessProfile, EngineType
from judgefinder.infrastructure.http.client import HttpClient

MUNICIPAL_RSS_SLUGS: set[str] = {
    "hanam",
    "cheorwon",
    "jecheon",
    "okcheon",
}

SKIP_COLLECTION_ACCESS_PROFILES: set[AccessProfile] = {
    AccessProfile.JS_RENDERED,
    AccessProfile.BLOCKED_WAF,
}

GENERIC_ENGINE_TYPES: set[EngineType] = {
    EngineType.SAEOL_GOSI,
    EngineType.EMINWON_OFR,
    EngineType.CITYNET_SAPGOSI,
    EngineType.INTEGRATED_SEARCH_GOSI,
    EngineType.GENERIC_EGOV_BBS,
    EngineType.JSON_LIST_API,
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

            if source_config.access_profile in SKIP_COLLECTION_ACCESS_PROFILES:
                sources.append(
                    NoopSource(
                        slug=source_config.slug,
                        municipality=source_config.municipality,
                        reason=(
                            f"access_profile={source_config.access_profile.value} "
                            f"(fallback={source_config.fallback_strategy.value})"
                        ),
                    )
                )
                continue

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
                sources.append(self._build_seongbuk_source(source_config))
                continue

            if slug == "pocheon":
                sources.append(self._build_pocheon_source(source_config))
                continue

            if slug in MUNICIPAL_RSS_SLUGS:
                sources.append(self._build_municipal_rss_source(source_config))
                continue

            if source_config.engine_type in GENERIC_ENGINE_TYPES:
                sources.append(self._build_generic_engine_source(source_config))
                continue

            if source_config.engine_type is not EngineType.UNKNOWN_ENGINE:
                sources.append(
                    NoopSource(
                        slug=source_config.slug,
                        municipality=source_config.municipality,
                        reason=(
                            f"engine_type={source_config.engine_type.value} not implemented "
                            f"(fallback={source_config.fallback_strategy.value})"
                        ),
                    )
                )
                continue

            raise ValueError(f"Unknown source slug: {slug}")

        return sources

    def list_enabled_source_slugs(self) -> list[str]:
        return list(self._config.enabled_sources)

    def _build_seongbuk_source(self, source_config: SourceConfig) -> SeongbukSource:
        strategy = source_config.request_strategy
        return SeongbukSource(
            slug=source_config.slug,
            municipality=source_config.municipality,
            source_type=source_config.source_type,
            list_url=source_config.list_url,
            fixture_path=source_config.fixture_path,
            timezone=self._timezone,
            http_client=self._http_client,
            timeout_seconds=strategy.timeout_seconds,
            max_retries=strategy.retries,
            use_session=strategy.session,
            include_referer=_should_include_referer(source_config),
        )

    def _build_pocheon_source(self, source_config: SourceConfig) -> PocheonEminwonSource:
        strategy = source_config.request_strategy
        return PocheonEminwonSource(
            slug=source_config.slug,
            municipality=source_config.municipality,
            source_type=source_config.source_type,
            list_url=source_config.list_url,
            fixture_path=source_config.fixture_path,
            timezone=self._timezone,
            http_client=self._http_client,
            timeout_seconds=strategy.timeout_seconds,
            max_retries=strategy.retries,
            use_session=strategy.session,
            include_referer=_should_include_referer(source_config),
        )

    def _build_municipal_rss_source(self, source_config: SourceConfig) -> MunicipalRssSource:
        strategy = source_config.request_strategy
        return MunicipalRssSource(
            slug=source_config.slug,
            municipality=source_config.municipality,
            source_type=source_config.source_type,
            list_url=source_config.list_url,
            fixture_path=source_config.fixture_path,
            timezone=self._timezone,
            http_client=self._http_client,
            timeout_seconds=strategy.timeout_seconds,
            max_retries=strategy.retries,
            use_session=strategy.session,
            include_referer=_should_include_referer(source_config),
        )

    def _build_generic_engine_source(self, source_config: SourceConfig) -> GenericEngineSource:
        strategy = source_config.request_strategy
        return GenericEngineSource(
            slug=source_config.slug,
            municipality=source_config.municipality,
            source_type=source_config.source_type,
            list_url=source_config.list_url,
            engine_type=source_config.engine_type,
            fixture_path=source_config.fixture_path,
            timezone=self._timezone,
            http_client=self._http_client,
            timeout_seconds=strategy.timeout_seconds,
            max_retries=strategy.retries,
            use_session=strategy.session,
            include_referer=_should_include_referer(source_config),
            throttle_seconds=strategy.throttle_seconds,
        )


def _should_include_referer(source_config: SourceConfig) -> bool:
    if source_config.request_strategy.referer:
        return True
    return source_config.access_profile in {
        AccessProfile.REFERER_REQUIRED,
        AccessProfile.SESSION_REQUIRED,
        AccessProfile.UNKNOWN_ACCESS,
    }
