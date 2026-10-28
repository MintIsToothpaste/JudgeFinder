from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from judgefinder.adapters.config import AppConfig, load_config

ROOT = Path(__file__).parents[2]


def read_cases(filename: str) -> dict[str, Any]:
    return json.loads((ROOT / "tests/fixtures" / filename).read_text(encoding="utf-8"))


@dataclass
class ProfileBatch:
    cases: dict[str, Any]
    settings: AppConfig
    recovered: dict[str, Any] = field(default_factory=dict)
    nomination: dict[str, Any] = field(default_factory=dict)


def load_batch(
    fixture: str,
    config: str,
    *,
    recovered: str | None = None,
    nomination: str | None = None,
    extras: tuple[tuple[str, tuple[str, ...]], ...] = (),
) -> ProfileBatch:
    cases = read_cases(fixture)
    for filename, slugs in extras:
        extra = read_cases(filename)
        cases.update({slug: extra[slug] for slug in slugs})
    return ProfileBatch(
        cases,
        load_config(ROOT / "config" / config),
        read_cases(recovered) if recovered else {},
        read_cases(nomination) if nomination else {},
    )


PROFILE_BATCHES = {
    "busan_daegu_ten": load_batch(
        "busan_daegu_ten_profiles.json", "batch-busan-daegu-ten.example.toml"
    ),
    "busan_ten": load_batch("busan_ten_profiles.json", "batch-busan-ten.example.toml"),
    "chungbuk_chungnam_jeonbuk_thirty": load_batch(
        "chungbuk_chungnam_jeonbuk_thirty_profiles.json",
        "batch-chungbuk-chungnam-jeonbuk-thirty.example.toml",
        recovered="chungbuk_chungnam_jeonbuk_recovered_profiles.json",
    ),
    "daegu_incheon_ten": load_batch(
        "daegu_incheon_ten_profiles.json", "batch-daegu-incheon-ten.example.toml"
    ),
    "daejeon_ulsan_sejong_gyeonggi_ten": load_batch(
        "daejeon_ulsan_sejong_gyeonggi_ten_profiles.json",
        "batch-daejeon-ulsan-sejong-gyeonggi-ten.example.toml",
    ),
    "gyeonggi_cities_next_ten": load_batch(
        "gyeonggi_cities_next_ten_profiles.json", "batch-gyeonggi-cities-next-ten.example.toml"
    ),
    "gyeonggi_cities_ten": load_batch(
        "gyeonggi_cities_ten_profiles.json", "batch-gyeonggi-cities-ten.example.toml"
    ),
    "gyeonggi_gangwon_chungbuk_thirty": load_batch(
        "gyeonggi_gangwon_chungbuk_thirty_profiles.json",
        "batch-gyeonggi-gangwon-chungbuk-thirty.example.toml",
    ),
    "gyeongnam_jeju_final": load_batch(
        "gyeongnam_jeju_final_profiles.json", "batch-gyeongnam-jeju-final-twenty.example.toml"
    ),
    "held_eighteen_recovered": load_batch(
        "held_eighteen_recovered_profiles.json", "batch-held-eighteen.example.toml"
    ),
    "incheon_jeonnam_ten": load_batch(
        "incheon_jeonnam_ten_profiles.json", "batch-incheon-jeonnam-ten.example.toml"
    ),
    "jeonbuk_gyeongbuk_gyeongnam_thirty": load_batch(
        "jeonbuk_gyeongbuk_gyeongnam_thirty_profiles.json",
        "batch-jeonbuk-gyeongbuk-gyeongnam-thirty.example.toml",
        recovered="jeonbuk_gyeongbuk_gyeongnam_recovered_profiles.json",
    ),
    "jeonnam_counties_ten": load_batch(
        "jeonnam_counties_ten_profiles.json",
        "batch-jeonnam-counties-ten.example.toml",
        nomination="gangjin_nomination_profile.json",
    ),
    "jeonnam_daejeon_ten": load_batch(
        "jeonnam_daejeon_ten_profiles.json", "batch-jeonnam-daejeon-ten.example.toml"
    ),
    "jeonnam_gwangju_ten": load_batch(
        "jeonnam_gwangju_ten_profiles.json", "batch-jeonnam-gwangju-ten.example.toml"
    ),
    "seoul_busan_ten": load_batch(
        "seoul_busan_ten_profiles.json",
        "batch-seoul-busan-ten.example.toml",
        extras=(
            ("cafe_five_recovered_profiles.json", ("seocho_katia", "busan_gosi")),
            ("cafe_four_recovered_profiles.json", ("gangnam_union6",)),
        ),
    ),
    "seoul_ten": load_batch(
        "seoul_ten_profiles.json",
        "batch-seoul-ten.example.toml",
        extras=(
            ("cafe_five_recovered_profiles.json", ("yangcheon_gosi", "gangbuk_gosi")),
            ("cafe_four_recovered_profiles.json", ("seodaemun_gosi", "mapo_gosi")),
        ),
    ),
}


def profile_cases(
    name: str,
    slugs: Iterable[str] | Callable[[ProfileBatch], Iterable[str]] | None = None,
) -> list[Any]:
    batch = PROFILE_BATCHES[name]
    if callable(slugs):
        slugs = slugs(batch)
    return [
        pytest.param(batch, slug, id=f"{name}-{slug}")
        for slug in (batch.cases if slugs is None else slugs)
    ]
