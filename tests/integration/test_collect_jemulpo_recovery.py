from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from bs4 import BeautifulSoup
from click.testing import CliRunner

from judgefinder.adapters.config import load_config
from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.infrastructure.http.client import RequestsHttpClient
from judgefinder.interfaces.cli.main import app

ROOT = Path(__file__).parents[2]


def test_original_disappearance_preserves_db_and_repost_keeps_its_registration_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads(
        (ROOT / "tests/fixtures/cafe_20261023_profiles.json").read_text(encoding="utf-8"),
    )
    slugs = ["jemulpo_notice", "jemulpo_khu"]
    example = ROOT / "config/batch-cafe-20261023.example.toml"
    settings = load_config(example)
    config, db = tmp_path / "config.toml", tmp_path / "notices.db"
    text = re.sub(
        r"^enabled_sources = .+$", "enabled_sources = " + json.dumps(slugs),
        example.read_text(encoding="utf-8"), flags=re.MULTILINE,
    )
    text = re.sub(r"^db_path = .+$", "db_path = " + json.dumps(db.as_posix()),
                  text, flags=re.MULTILINE)
    config.write_text(text.replace("throttle_seconds = 0.3", "throttle_seconds = 0.0"),
                      encoding="utf-8")
    phase = 0
    requests: list[str] = []

    def get_text(
        self: RequestsHttpClient, url: str, timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None, use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        assert use_session and verify_tls and headers and "Referer" in headers
        requests.append(url)
        slug = "jemulpo_khu" if urlparse(url).hostname == "kbiz.khu.ac.kr" else "jemulpo_notice"
        case = cases[slug]
        if url == case["url"]:
            assert slug == "jemulpo_notice" and phase == 0 or slug == "jemulpo_khu" and phase > 0
            return str(case["detail_html"])
        profile = settings.sources[slug].html_profile
        assert profile is not None
        query = parse_qs(urlparse(url).query)
        page = int(query[profile.page_param][0])
        if slug == "jemulpo_khu":
            # The site search stays scoped to Jemulpo instead of all evaluator notices.
            assert query["searchKeyword"] == ["제물포구"]
            assert query["searchCondition"] == ["1"]
        soup = BeautifulSoup(case["list_html"], "html5lib")
        container = soup.select_one(profile.container_selector)
        assert container is not None
        if page > 1 or (slug == "jemulpo_notice") != (phase == 0):
            container.clear()
        return str(soup)

    monkeypatch.setattr(RequestsHttpClient, "get_text", get_text)
    runner = CliRunner()
    args = ["--config-path", str(config)]
    window = ["--date", "2026-10-28", "--days", "7"]
    with caplog.at_level(logging.WARNING):
        first = runner.invoke(app, [*args, "collect", *window])
        assert first.exit_code == 0, first.output
        assert first.stdout.splitlines() == [cases["jemulpo_notice"]["url"]]
        with sqlite3.connect(db) as connection:
            assert connection.execute("select published_date from notices").fetchall() == [
                ("2026-10-22",),
            ]
        phase = 1
        for _ in range(2):
            result = runner.invoke(app, [*args, "collect", *window])
            assert result.exit_code == 0, result.output
            assert result.stdout.splitlines() == [cases["jemulpo_khu"]["url"]]
        assert "Skipping source" not in caplog.text
    with sqlite3.connect(db) as connection:
        rows = connection.execute(
            "select municipality,title,published_date,url from notices order by published_date",
        ).fetchall()
    assert rows == [
        (settings.sources[slug].municipality, cases[slug]["title"],
         cases[slug]["date"], cases[slug]["url"]) for slug in slugs
    ]
    count = len(requests)
    listed = runner.invoke(app, [*args, "list", *window])
    assert listed.exit_code == 0
    assert set(listed.stdout.splitlines()) == {cases[slug]["url"] for slug in slugs}
    assert len(requests) == count


def test_repost_registration_date_cannot_be_replaced_by_original_or_application_date() -> None:
    cases = json.loads(
        (ROOT / "tests/fixtures/cafe_20261023_profiles.json").read_text(encoding="utf-8"),
    )
    case = cases["jemulpo_khu"]
    source = load_config(ROOT / case["config_path"]).sources["jemulpo_khu"]
    assert source.html_profile is not None
    detail = case["detail_html"].replace("2026-10-27", "2026-02-30")
    detail += "<p>구청 작성일 2026-10-22. 모집기간: 2026-10-16 ~ 2026-10-27</p>"
    with pytest.raises(ValueError, match="invalid title or registration date"):
        parse_profiled_html(
            case["list_html"], list_url=source.list_url, profile=source.html_profile,
            detail_loader=lambda _: detail,
        )


def test_official_detail_redirect_response_does_not_become_a_notice() -> None:
    cases = json.loads(
        (ROOT / "tests/fixtures/cafe_20261023_profiles.json").read_text(encoding="utf-8"),
    )
    case = cases["jemulpo_notice"]
    source = load_config(ROOT / case["config_path"]).sources["jemulpo_notice"]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="registration-date element missing"):
        parse_profiled_html(
            case["list_html"], list_url=source.list_url, profile=source.html_profile,
            detail_loader=lambda _: "<title>인천광역시 제물포구청</title><p>공고 목록 더보기</p>",
        )
