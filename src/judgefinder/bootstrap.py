from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from judgefinder.adapters.config import AppConfig, load_config
from judgefinder.adapters.origin_discovery import (
    CommitteeOriginDiscovery,
    FileOriginDiscovery,
    HibrainOriginDiscovery,
)
from judgefinder.adapters.origin_reader import ConfiguredOriginReader
from judgefinder.adapters.source_registry import SourceRegistry
from judgefinder.application.origins import CollectOriginNoticesUseCase
from judgefinder.application.use_cases import CollectNoticesUseCase, ListNoticesUseCase
from judgefinder.domain.origins import OriginDiscovery
from judgefinder.infrastructure.db.origins import SqlAlchemyOriginStore
from judgefinder.infrastructure.db.repository import SqlAlchemyNoticeRepository
from judgefinder.infrastructure.db.session import (
    create_schema,
    create_session_factory,
    create_sqlite_engine,
)
from judgefinder.infrastructure.http.client import RequestsHttpClient


@dataclass(slots=True)
class AppContainer:
    config: AppConfig
    timezone: ZoneInfo
    source_registry: SourceRegistry
    collect_use_case: CollectNoticesUseCase
    list_use_case: ListNoticesUseCase
    origin_use_case: CollectOriginNoticesUseCase | None = None
    origin_store: SqlAlchemyOriginStore | None = None


def create_app(config_path: str | Path = "config/config.toml") -> AppContainer:
    resolved_config_path = Path(config_path).resolve()
    base_dir = _infer_base_dir(resolved_config_path)
    config = load_config(resolved_config_path, base_dir=base_dir)

    timezone = ZoneInfo(config.timezone)
    config.db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_sqlite_engine(config.db_path)
    create_schema(engine)
    session_factory = create_session_factory(engine)
    repository = SqlAlchemyNoticeRepository(session_factory)

    http_client = RequestsHttpClient()
    source_registry = SourceRegistry(config=config, http_client=http_client, timezone=timezone)
    sources = source_registry.build_enabled_sources()

    collect_use_case = CollectNoticesUseCase(repository=repository, sources=sources)
    list_use_case = ListNoticesUseCase(repository=repository)
    origin_store = SqlAlchemyOriginStore(session_factory)
    origin_use_case = None
    recovery = config.origin_recovery
    if recovery.enabled:
        discoveries: list[OriginDiscovery] = []
        if recovery.hibrain:
            discoveries.append(HibrainOriginDiscovery(
                http_client, max_pages=recovery.max_pages,
                timeout_seconds=recovery.timeout_seconds,
                throttle_seconds=recovery.throttle_seconds,
            ))
        if recovery.candidate_file is not None:
            discoveries.append(FileOriginDiscovery(recovery.candidate_file))
        if recovery.committee_search:
            discoveries.extend(
                discovery for source in sources
                for discovery in CommitteeOriginDiscovery.for_source(source)
            )
        origin_use_case = CollectOriginNoticesUseCase(
            origin_store, ConfiguredOriginReader(sources), discoveries,
            committee_search=recovery.committee_search,
        )

    return AppContainer(
        config=config,
        timezone=timezone,
        source_registry=source_registry,
        collect_use_case=collect_use_case,
        list_use_case=list_use_case,
        origin_use_case=origin_use_case,
        origin_store=origin_store,
    )


def _infer_base_dir(config_path: Path) -> Path:
    if config_path.parent.name == "config":
        return config_path.parent.parent
    return config_path.parent
