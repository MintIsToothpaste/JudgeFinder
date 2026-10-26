from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from judgefinder.adapters.config import AppConfig, SourceConfig
from judgefinder.adapters.source_registry import SourceRegistry
from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.adapters.sources.municipal_rss.source import MunicipalRssSource
from judgefinder.adapters.sources.noop.source import NoopSource
from judgefinder.adapters.sources.pocheon_eminwon.source import PocheonEminwonSource
from judgefinder.domain.entities import SourceType
from judgefinder.domain.source_profiles import (
    AccessProfile,
    EngineType,
    FallbackStrategy,
    RequestStrategy,
)
from judgefinder.infrastructure.http.client import HttpResponse


class DummyHttpClient:
    def get_text(
        self,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        _ = url
        _ = timeout_seconds
        _ = headers
        _ = use_session
        _ = verify_tls
        return ""

    def get_response(
        self,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
        verify_tls: bool = True,
    ) -> HttpResponse:
        _ = url
        _ = timeout_seconds
        _ = headers
        _ = use_session
        _ = verify_tls
        return HttpResponse(status_code=200, text="", headers={}, url=url)


@pytest.mark.parametrize("source_type", [SourceType.HTML, SourceType.API])
def test_source_registry_routes_hanam_to_configured_generic_engine(
    source_type: SourceType,
) -> None:
    source_config = SourceConfig(
        slug="hanam",
        municipality="Hanam",
        source_type=source_type,
        list_url="https://www.hanam.go.kr/www/selectGosiList.do?key=171&searchCnd=SJ",
        engine_type=EngineType.GENERIC_EGOV_BBS,
    )
    config = AppConfig(
        timezone="Asia/Seoul",
        db_path=Path("data/judgefinder.db"),
        enabled_sources=["hanam"],
        sources={"hanam": source_config},
    )
    registry = SourceRegistry(config, DummyHttpClient(), ZoneInfo("Asia/Seoul"))
    sources = registry.build_enabled_sources()

    assert len(sources) == 1
    assert isinstance(sources[0], GenericEngineSource)


@pytest.mark.parametrize("slug", ["jecheon", "cheorwon", "okcheon"])
def test_source_registry_preserves_other_municipal_rss_adapters(slug: str) -> None:
    config = AppConfig(
        timezone="Asia/Seoul",
        db_path=Path("data/judgefinder.db"),
        enabled_sources=[slug],
        sources={
            slug: SourceConfig(
                slug=slug,
                municipality=slug,
                source_type=SourceType.API,
                list_url=f"https://www.{slug}.go.kr/rssBbsNtt.do?bbsNo=18",
            ),
        },
    )
    registry = SourceRegistry(config, DummyHttpClient(), ZoneInfo("Asia/Seoul"))
    sources = registry.build_enabled_sources()

    assert len(sources) == 1
    assert isinstance(sources[0], MunicipalRssSource)


def test_source_registry_selects_generic_engine_adapter_for_non_pocheon_eminwon() -> None:
    source_config = SourceConfig(
        slug="any-city",
        municipality="Any City",
        source_type=SourceType.HTML,
        list_url="https://eminwon.any.go.kr/ofr/OfrAction.do",
        fixture_path=None,
        engine_type=EngineType.EMINWON_OFR,
        access_profile=AccessProfile.SESSION_REQUIRED,
        request_strategy=RequestStrategy(session=True, referer=True, retries=4),
        fallback_strategy=FallbackStrategy.NONE,
    )
    config = AppConfig(
        timezone="Asia/Seoul",
        db_path=Path("data/judgefinder.db"),
        enabled_sources=["any-city"],
        sources={"any-city": source_config},
    )

    registry = SourceRegistry(
        config=config,
        http_client=DummyHttpClient(),
        timezone=ZoneInfo("Asia/Seoul"),
    )
    sources = registry.build_enabled_sources()

    assert len(sources) == 1
    source = sources[0]
    assert isinstance(source, GenericEngineSource)
    assert source.use_session is True
    assert source.max_retries == 4
    assert source.verify_tls is True


def test_source_registry_keeps_pocheon_specialized_adapter() -> None:
    source_config = SourceConfig(
        slug="pocheon",
        municipality="Pocheon",
        source_type=SourceType.HTML,
        list_url="https://www.pocheon.go.kr/www/selectEminwonList.do?key=12563",
        fixture_path=None,
        engine_type=EngineType.EMINWON_OFR,
        access_profile=AccessProfile.OPEN,
        request_strategy=RequestStrategy(session=False, referer=True, retries=3),
        fallback_strategy=FallbackStrategy.NONE,
    )
    config = AppConfig(
        timezone="Asia/Seoul",
        db_path=Path("data/judgefinder.db"),
        enabled_sources=["pocheon"],
        sources={"pocheon": source_config},
    )

    registry = SourceRegistry(
        config=config,
        http_client=DummyHttpClient(),
        timezone=ZoneInfo("Asia/Seoul"),
    )
    sources = registry.build_enabled_sources()

    assert len(sources) == 1
    assert isinstance(sources[0], PocheonEminwonSource)


def test_source_registry_allows_cheorwon_to_use_generic_engine_when_configured() -> None:
    source_config = SourceConfig(
        slug="cheorwon",
        municipality="Cheorwon",
        source_type=SourceType.HTML,
        list_url="https://www.cwg.go.kr/www/selectBbsNttList.do?bbsNo=25&key=1226&pageIndex=1",
        fixture_path=None,
        engine_type=EngineType.GENERIC_EGOV_BBS,
        access_profile=AccessProfile.UNKNOWN_ACCESS,
        request_strategy=RequestStrategy(verify_tls=False),
        fallback_strategy=FallbackStrategy.NONE,
    )
    config = AppConfig(
        timezone="Asia/Seoul",
        db_path=Path("data/judgefinder.db"),
        enabled_sources=["cheorwon"],
        sources={"cheorwon": source_config},
    )

    registry = SourceRegistry(
        config=config,
        http_client=DummyHttpClient(),
        timezone=ZoneInfo("Asia/Seoul"),
    )
    sources = registry.build_enabled_sources()

    assert len(sources) == 1
    assert isinstance(sources[0], GenericEngineSource)
    assert not isinstance(sources[0], MunicipalRssSource)
    assert sources[0].verify_tls is False


def test_source_registry_skips_blocked_waf_sources() -> None:
    source_config = SourceConfig(
        slug="blocked-city",
        municipality="Blocked City",
        source_type=SourceType.HTML,
        list_url="https://blocked.example.com/list",
        fixture_path=None,
        engine_type=EngineType.GENERIC_EGOV_BBS,
        access_profile=AccessProfile.BLOCKED_WAF,
        request_strategy=RequestStrategy(),
        fallback_strategy=FallbackStrategy.MANUAL_REVIEW,
    )
    config = AppConfig(
        timezone="Asia/Seoul",
        db_path=Path("data/judgefinder.db"),
        enabled_sources=["blocked-city"],
        sources={"blocked-city": source_config},
    )

    registry = SourceRegistry(
        config=config,
        http_client=DummyHttpClient(),
        timezone=ZoneInfo("Asia/Seoul"),
    )
    sources = registry.build_enabled_sources()

    assert len(sources) == 1
    assert isinstance(sources[0], NoopSource)


def test_source_registry_skips_manual_review_fallback_sources() -> None:
    source_config = SourceConfig(
        slug="manual-city",
        municipality="Manual City",
        source_type=SourceType.HTML,
        list_url="https://manual.example.com/list",
        fixture_path=None,
        engine_type=EngineType.GENERIC_EGOV_BBS,
        access_profile=AccessProfile.UNKNOWN_ACCESS,
        request_strategy=RequestStrategy(),
        fallback_strategy=FallbackStrategy.MANUAL_REVIEW,
    )
    config = AppConfig(
        timezone="Asia/Seoul",
        db_path=Path("data/judgefinder.db"),
        enabled_sources=["manual-city"],
        sources={"manual-city": source_config},
    )

    registry = SourceRegistry(
        config=config,
        http_client=DummyHttpClient(),
        timezone=ZoneInfo("Asia/Seoul"),
    )
    sources = registry.build_enabled_sources()

    assert len(sources) == 1
    assert isinstance(sources[0], NoopSource)
