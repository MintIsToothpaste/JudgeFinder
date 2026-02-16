from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python < 3.11 fallback
    import tomli as tomllib

from judgefinder.domain.entities import SourceType


@dataclass(slots=True)
class SourceConfig:
    slug: str
    municipality: str
    source_type: SourceType
    list_url: str
    fixture_path: Path | None = None


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
        fixture_path_raw = value.get("fixture_path")
        fixture_path = (
            _resolve_path(fixture_path_raw, resolved_base_dir)
            if isinstance(fixture_path_raw, str) and fixture_path_raw
            else None
        )
        sources[slug] = SourceConfig(
            slug=slug,
            municipality=municipality,
            source_type=source_type,
            list_url=list_url,
            fixture_path=fixture_path,
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


def _resolve_path(path_str: str, base_dir: Path) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()
