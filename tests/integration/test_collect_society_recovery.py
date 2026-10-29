from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from datetime import date
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
CASES = json.loads((ROOT / "tests/fixtures/hibrain_recovery_societies.json").read_text("utf-8"))


def test_public_html_and_json_routes_collect_reposts_and_replay_without_duplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    example = ROOT / "config/batch-hibrain-recovery.example.toml"
    db = tmp_path / "societies.db"
    config = tmp_path / "config.toml"
    text = re.sub(r"^db_path = .+$", "db_path = " + json.dumps(db.as_posix()),
                  example.read_text("utf-8"), flags=re.MULTILINE)
    text = re.sub(r"^enabled_sources = .+$", "enabled_sources = " + json.dumps(list(CASES)),
                  text, flags=re.MULTILINE)
    config.write_text(text.replace("throttle_seconds = 0.3", "throttle_seconds = 0.0"), "utf-8")
    responses = {r["url"]: r["body"] for case in CASES.values() for r in case["responses"]}
    calls: list[str] = []

    def get_text(
        self: RequestsHttpClient, url: str, timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None, use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        assert use_session and verify_tls and headers and "Referer" in headers
        assert url in responses, f"Unexpected live request in offline test: {url}"
        calls.append(url)
        query = parse_qs(urlparse(url).query, encoding="euc-kr" if "railway" in url else "utf-8")
        if "/article.json" in url:
            assert query["search[value]"] == ["평가위원"]
            assert query["start"] == [str((int(query["draw"][0]) - 1) * 15)]
        if "/lists?" in url:
            assert query["s_opt0"] == ["bo_title"] and query["s_text0"] == ["평가위원"]
            assert "pageIndex" not in query and "page" not in query
        if "Action=search" in url:
            assert query["search_name"] == ["평가위원"]
            assert "%C6%F2%B0%A1%C0%A7%BF%F8" in url
        return str(responses[url])

    monkeypatch.setattr(RequestsHttpClient, "get_text", get_text)
    expected = {
        (n["municipality"], n["title"], n["published_date"], n["url"], n["source_type"])
        for case in CASES.values() for n in case["notices"]
    }
    runner = CliRunner()
    args = ["--config-path", str(config)]
    for _ in range(2):
        result = runner.invoke(app, [*args, "collect", "--date", "2026-10-29", "--days", "38"])
        assert result.exit_code == 0, result.output
        assert "Skipping source" not in caplog.text
        assert set(result.stdout.splitlines()) == {n[3] for n in expected}
        with sqlite3.connect(db) as connection:
            rows = connection.execute(
                "select municipality,title,published_date,url,source_type from notices",
            ).fetchall()
        assert len(rows) == 7 and set(rows) == expected
    assert all(calls.count(url) == 2 for url in responses)
    count = len(calls)
    listed = runner.invoke(app, [*args, "list", "--date", "2026-10-29", "--days", "38"])
    assert listed.exit_code == 0 and set(listed.stdout.splitlines()) == {n[3] for n in expected}
    assert len(calls) == count


@pytest.mark.parametrize("slug", ["kila_news", "railway_notices"])
def test_repost_requires_its_own_explicit_detail_publication_date(slug: str) -> None:
    setting = load_config(ROOT / CASES[slug]["config_path"]).sources[slug]
    profile = setting.html_profile
    assert profile is not None
    responses = CASES[slug]["responses"]
    listing = responses[0]["body"]
    details = {r["url"]: r["body"] for r in responses}

    def missing_date(url: str) -> str:
        soup = BeautifulSoup(details[url], "html5lib")
        node = soup.select_one(profile.detail_date_selector)
        assert node is not None
        node.decompose()
        return (str(soup)
                + "<footer>하이브레인 등록일 2026-10-01. 모집기간 2026-10-13~10-20</footer>")

    with pytest.raises(ValueError, match="registration-date element missing"):
        parse_profiled_html(
            listing, list_url=setting.list_url, profile=profile, detail_loader=missing_date,
            detail_not_before=date(2026, 9, 22), expected_page=1,
        )


def test_reposts_keep_publishers_and_have_no_runtime_fixtures_or_pinned_notice_ids() -> None:
    settings = load_config(ROOT / "config/batch-hibrain-recovery.example.toml")
    assert set(CASES).issubset(settings.enabled_sources)
    for slug, case in CASES.items():
        setting = settings.sources[slug]
        assert setting.fixture_path is None
        assert setting.request_strategy.verify_tls
        assert setting.municipality in {"한국가스학회", "한국조경학회", "한국철도학회"}
        for notice in case["notices"]:
            query = parse_qs(urlparse(notice["url"]).query)
            path_id = urlparse(notice["url"]).path.split("/")[-1]
            identifier = query.get("bo_id", query.get("b_code", [path_id]))[0]
            assert identifier not in setting.list_url
