from __future__ import annotations

from pathlib import Path

import pytest

from judgefinder.adapters.config import load_config
from judgefinder.domain.source_profiles import (
    AccessProfile,
    EngineType,
    FallbackStrategy,
)


def test_load_config_uses_default_engine_access_and_strategy(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                'timezone = "Asia/Seoul"',
                'db_path = "data/judgefinder.db"',
                'enabled_sources = ["demo"]',
                "",
                "[sources.demo]",
                'municipality = "demo-city"',
                'source_type = "html"',
                'list_url = "https://example.com/list"',
            ]
        ),
        encoding="utf-8",
    )

    app_config = load_config(config_path, base_dir=tmp_path)
    source = app_config.sources["demo"]

    assert source.engine_type is EngineType.UNKNOWN_ENGINE
    assert source.access_profile is AccessProfile.UNKNOWN_ACCESS
    assert source.fallback_strategy is FallbackStrategy.NONE
    assert source.request_strategy.session is False
    assert source.request_strategy.referer is False
    assert source.request_strategy.retries == 3


def test_load_config_parses_new_source_profile_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                'timezone = "Asia/Seoul"',
                'db_path = "data/judgefinder.db"',
                'enabled_sources = ["demo"]',
                "",
                "[sources.demo]",
                'municipality = "demo-city"',
                'source_type = "html"',
                'list_url = "https://example.com/list"',
                'engine_type = "eminwon_ofr"',
                'access_profile = "session_required"',
                'fallback_strategy = "manual_review"',
                "",
                "[sources.demo.request_strategy]",
                "session = true",
                "referer = true",
                "retries = 7",
                "timeout_seconds = 15.5",
                "throttle_seconds = 0.4",
            ]
        ),
        encoding="utf-8",
    )

    app_config = load_config(config_path, base_dir=tmp_path)
    source = app_config.sources["demo"]

    assert source.engine_type is EngineType.EMINWON_OFR
    assert source.access_profile is AccessProfile.SESSION_REQUIRED
    assert source.fallback_strategy is FallbackStrategy.MANUAL_REVIEW
    assert source.request_strategy.session is True
    assert source.request_strategy.referer is True
    assert source.request_strategy.retries == 7
    assert source.request_strategy.timeout_seconds == 15.5
    assert source.request_strategy.throttle_seconds == 0.4


def test_load_config_raises_for_invalid_engine_type(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                'timezone = "Asia/Seoul"',
                'db_path = "data/judgefinder.db"',
                'enabled_sources = ["demo"]',
                "",
                "[sources.demo]",
                'municipality = "demo-city"',
                'source_type = "html"',
                'list_url = "https://example.com/list"',
                'engine_type = "invalid_type"',
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid value for 'engine_type'"):
        load_config(config_path, base_dir=tmp_path)
