from __future__ import annotations

from pathlib import Path

import pytest

from judgefinder.adapters.config import load_config
from judgefinder.domain.source_profiles import (
    AccessProfile,
    EngineType,
    FallbackStrategy,
    HtmlProfile,
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
    assert source.recruitment_only is False
    assert source.request_strategy.session is False
    assert source.request_strategy.referer is False
    assert source.request_strategy.retries == 3
    assert source.request_strategy.verify_tls is True


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
                "verify_tls = false",
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
    assert source.request_strategy.verify_tls is False


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


@pytest.mark.parametrize("extra", [
    'unexpected = "typo"', 'date_selector = 5',
    'date_selector = ""', 'id_pattern = "id=([0-9]+)"',
    'page_size = true', 'page_size = "10"',
    'offset_param = "pageIndex"', 'link_attribute = "data-key-no"',
])
def test_load_config_rejects_invalid_html_profiles(tmp_path: Path, extra: str) -> None:
    config = tmp_path / "profile.toml"
    config.write_text(
        'timezone = "Asia/Seoul"\ndb_path = "data/test.db"\nenabled_sources = ["demo"]\n'
        '[sources.demo]\nmunicipality = "demo"\nsource_type = "html"\n'
        'engine_type = "generic_egov_bbs"\nlist_url = "https://example.org/list"\n'
        '[sources.demo.html_profile]\ncontainer_selector = "table"\n'
        'row_selector = "tbody tr"\n'
        + ('' if extra.startswith('date_selector') else 'date_selector = "td.date"\n')
        + extra + '\n', encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_config(config)


@pytest.mark.parametrize(("pattern", "template"), [
    (r"id=[0-9]+", "/view?id={id}"),
    (r"id=([0-9]+)(x)", "/view?id={id}"),
    (r"id=([0-9]+)", "/view?id={unknown}"),
    (r"id=([0-9]+)", "/view?id={id}&duplicate={id}"),
])
def test_html_profile_requires_unambiguous_identity(pattern: str, template: str) -> None:
    with pytest.raises(ValueError):
        HtmlProfile(
            container_selector="table", row_selector="tr", date_selector="td.date",
            id_pattern=pattern, detail_url_template=template,
        )
