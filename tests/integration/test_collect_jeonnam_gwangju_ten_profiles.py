from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from click.testing import CliRunner

from judgefinder.adapters.config import load_config
from judgefinder.infrastructure.http.client import RequestsHttpClient
from judgefinder.interfaces.cli.main import app

ROOT = Path(__file__).parents[2]


def test_real_profiles_collection_pagination_deduplication_and_offline_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    cases = json.loads((ROOT / "tests/fixtures/jeonnam_gwangju_ten_profiles.json").read_text())
    example = ROOT / "config/batch-jeonnam-gwangju-ten.example.toml"
    settings = load_config(example)
    config, db = tmp_path / "config.toml", tmp_path / "notices.db"
    config.write_text(example.read_text().replace(
        "data/live-tests/jeonnam-gwangju-ten-2026-10-04/notices.db", db.as_posix(),
    ).replace("throttle_seconds = 1.0", "throttle_seconds = 0.0"), encoding="utf-8")
    assert load_config(config).db_path == db
    details = {case["url"]: case for case in cases.values() if "detail_html" in case}
    calls: list[str] = []

    def get_text(
        self: RequestsHttpClient, url: str, timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None, use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        assert verify_tls and use_session and headers is not None and "Referer" in headers
        calls.append(url)
        if url in details:
            return str(details[url]["detail_html"])
        parsed, query = urlparse(url), parse_qs(urlparse(url).query)
        source = next(s for s in settings.sources.values()
            if (urlparse(s.list_url).netloc, urlparse(s.list_url).path)
            == (parsed.netloc, parsed.path)
            and all(query.get(k) == v for k, v in parse_qs(urlparse(s.list_url).query).items()))
        profile, case = source.html_profile or source.json_profile, cases[source.slug]
        assert profile is not None
        page = int(query[profile.page_param][0])
        assert page in (1, 2)
        if source.json_profile:
            assert query["BEGIN_ROW_IDX"] == [str((page - 1) * 10 + 1)]
            data = json.loads(case["list_json"])
            if page == 2:
                data["RSLT_DATA"]["searchList"]["pageMap"]["nowPage"] = "2"
                data["RSLT_DATA"]["searchList"]["dataMap"] = []
            return json.dumps(data, ensure_ascii=False)
        if source.slug == "suncheon" and page == 2:
            return '<table class="bbsList"><tbody><tr><td>검색 결과가 없습니다.</td></tr>' \
                '</tbody></table><a class="on" title="현재페이지">2</a>'
        return str(case.get("list_html", case.get("empty_list_html")))

    monkeypatch.setattr(RequestsHttpClient, "get_text", get_text)
    runner, args = CliRunner(), ["--config-path", str(config)]
    window = ["--date", "2026-10-04", "--days", "365"]
    outputs = []
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            result = runner.invoke(app, [*args, "collect", *window])
            assert result.exit_code == 0, result.output
            outputs.append(result.stdout)
    assert "Skipping source" not in caplog.text and outputs[0] == outputs[1]
    positive = {slug: c for slug, c in cases.items() if c.get("category") == "recruitment"}
    assert len(positive) == 10 and len(outputs[0].splitlines()) == 10
    with sqlite3.connect(db) as conn:
        actual = conn.execute(
            "select municipality,title,published_date,url from notices order by municipality",
        ).fetchall()
    assert actual == sorted((settings.sources[slug].municipality, c["title"], c["date"], c["url"])
        for slug, c in positive.items())
    count = len(calls)
    listed = runner.invoke(app, [*args, "list", *window])
    assert listed.exit_code == 0 and listed.stdout == outputs[0] and len(calls) == count
