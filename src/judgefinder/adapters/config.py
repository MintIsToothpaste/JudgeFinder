from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python < 3.11 fallback
    import tomli as tomllib

from judgefinder.domain.entities import SourceType
from judgefinder.domain.source_profiles import (
    AccessProfile,
    EngineType,
    FallbackStrategy,
    RequestStrategy,
)

EnumT = TypeVar("EnumT", bound=Enum)


@dataclass(slots=True)
class SourceConfig:
    slug: str
    municipality: str
    source_type: SourceType
    list_url: str
    fixture_path: Path | None = None
    engine_type: EngineType = EngineType.UNKNOWN_ENGINE
    access_profile: AccessProfile = AccessProfile.UNKNOWN_ACCESS
    request_strategy: RequestStrategy = field(default_factory=RequestStrategy)
    fallback_strategy: FallbackStrategy = FallbackStrategy.NONE


@dataclass(slots=True)
class AppConfig:
    timezone: str
    db_path: Path
    enabled_sources: list[str]
    sources: dict[str, SourceConfig]


def load_config(config_path: Path, base_dir: Path | None = None) -> AppConfig:
    resolved_base_dir = base_dir or Path.cwd()
    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))

    timezone = _read_required_str(raw, "timezone")
    db_path = _resolve_path(_read_required_str(raw, "db_path"), resolved_base_dir)
    enabled_sources = _read_required_list(raw, "enabled_sources")
    sources_raw = raw.get("sources")
    if not isinstance(sources_raw, dict):
        raise ValueError("Missing or invalid [sources] table in config.")

    sources: dict[str, SourceConfig] = {}
    for slug, value in sources_raw.items():
        if not isinstance(value, dict):
            raise ValueError(f"Invalid source config for '{slug}'.")
        municipality = _read_required_str(value, "municipality")
        source_type = SourceType(_read_required_str(value, "source_type"))
        list_url = _read_required_str(value, "list_url")
        engine_type = _read_optional_enum(
            value,
            "engine_type",
            EngineType,
            default=EngineType.UNKNOWN_ENGINE,
        )
        access_profile = _read_optional_enum(
            value,
            "access_profile",
            AccessProfile,
            default=AccessProfile.UNKNOWN_ACCESS,
        )
        fixture_path_raw = value.get("fixture_path")
        fixture_path = (
            _resolve_path(fixture_path_raw, resolved_base_dir)
            if isinstance(fixture_path_raw, str) and fixture_path_raw
            else None
        )
        request_strategy = _read_request_strategy(
            value.get("request_strategy"),
            access_profile=access_profile,
        )
        fallback_strategy = _read_optional_enum(
            value,
            "fallback_strategy",
            FallbackStrategy,
            default=_default_fallback_strategy(access_profile),
        )
        sources[slug] = SourceConfig(
            slug=slug,
            municipality=municipality,
            source_type=source_type,
            list_url=list_url,
            fixture_path=fixture_path,
            engine_type=engine_type,
            access_profile=access_profile,
            request_strategy=request_strategy,
            fallback_strategy=fallback_strategy,
        )

    return AppConfig(
        timezone=timezone,
        db_path=db_path,
        enabled_sources=enabled_sources,
        sources=sources,
    )


def _read_required_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing or invalid string key: {key}")
    return value


def _read_required_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"Missing or invalid list key: {key}")
    return list(value)


def _read_optional_enum(
    data: dict[str, Any],
    key: str,
    enum_cls: type[EnumT],
    *,
    default: EnumT,
) -> EnumT:
    value = data.get(key)
    if value is None:
        return default
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Invalid enum key '{key}'.")
    try:
        return enum_cls(value.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid value for '{key}': {value}") from exc


def _read_request_strategy(
    value: Any,
    *,
    access_profile: AccessProfile,
) -> RequestStrategy:
    default_strategy = RequestStrategy.from_access_profile(access_profile)
    if value is None:
        return default_strategy
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "session":
            return RequestStrategy(session=True, referer=True)
        if normalized == "referer":
            return RequestStrategy(referer=True)
        if normalized == "retry":
            return RequestStrategy(retries=5)
        raise ValueError(f"Invalid request_strategy value: {value}")
    if not isinstance(value, dict):
        raise ValueError("request_strategy must be a table or string.")

    session = _read_optional_bool(value, "session", default=default_strategy.session)
    referer = _read_optional_bool(value, "referer", default=default_strategy.referer)
    retries = _read_optional_int(value, "retries", default=default_strategy.retries, min_value=1)
    timeout_seconds = _read_optional_float(
        value,
        "timeout_seconds",
        default=default_strategy.timeout_seconds,
        min_value=0.1,
    )
    throttle_seconds = _read_optional_float(
        value,
        "throttle_seconds",
        default=default_strategy.throttle_seconds,
        min_value=0.0,
    )
    return RequestStrategy(
        session=session,
        referer=referer,
        retries=retries,
        timeout_seconds=timeout_seconds,
        throttle_seconds=throttle_seconds,
    )


def _read_optional_bool(data: dict[str, Any], key: str, *, default: bool) -> bool:
    value = data.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"Invalid bool value for '{key}'.")
    return value


def _read_optional_int(data: dict[str, Any], key: str, *, default: int, min_value: int) -> int:
    value = data.get(key)
    if value is None:
        return default
    if not isinstance(value, int) or value < min_value:
        raise ValueError(f"Invalid int value for '{key}'.")
    return value


def _read_optional_float(
    data: dict[str, Any],
    key: str,
    *,
    default: float,
    min_value: float,
) -> float:
    value = data.get(key)
    if value is None:
        return default
    if not isinstance(value, (int, float)):
        raise ValueError(f"Invalid float value for '{key}'.")
    float_value = float(value)
    if float_value < min_value:
        raise ValueError(f"Invalid float value for '{key}'.")
    return float_value


def _default_fallback_strategy(access_profile: AccessProfile) -> FallbackStrategy:
    if access_profile is AccessProfile.JS_RENDERED:
        return FallbackStrategy.API_BACKTRACK
    if access_profile is AccessProfile.BLOCKED_WAF:
        return FallbackStrategy.MANUAL_REVIEW
    return FallbackStrategy.NONE


def _resolve_path(path_str: str, base_dir: Path) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()
