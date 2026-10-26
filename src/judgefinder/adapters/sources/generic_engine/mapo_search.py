from __future__ import annotations

import json
import re
from urllib.parse import quote, urlencode, urljoin, urlparse

from judgefinder.adapters.sources.generic_engine.parser import _extract_date_from_text
from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource


class MapoSearchSource(GenericEngineSource):
    """Read-only requests used by Mapo's public integrated-search page.

    The ordinary notice list omits some still-public recruitment notices.
    The search proxy and index are specific to this site's published search.js.
    """

    def _load_page(self, *, page_index: int) -> str:
        if self.fixture_path is not None:
            return self.fixture_path.read_text(encoding="utf-8")
        if page_index in self.page_cache:
            return self.page_cache[page_index]
        query = {
            "query": {"multi_match": {
                "query": "#query#", "fields": ["ba_title"], "operator": "and",
            }},
            "size": 10, "from": (page_index - 1) * 10,
            "sort": [{"ba_regdate": {"order": "desc"}}],
        }
        body = urlencode({
            "requestMethod": "GET",
            "esUrl": "http://98.14.1.230:9200/_msearch",
            "objData": json.dumps({"index": "mapo_board"}) + "\n"
            + json.dumps(query) + "\n",
            "uriQuery": quote(self.search_keyword),
        })
        payload = self._request_text(f"{self.list_url}?{body}", post=True)
        normalized = normalize_search_response(payload, list_url=self.list_url)
        self.page_cache[page_index] = normalized
        return normalized


def normalize_search_response(payload: str, *, list_url: str) -> str:
    data = json.loads(payload)
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict) or not isinstance(data.get("responses"), list):
        raise ValueError("Mapo search response missing results")
    responses = data["responses"]
    if len(responses) != 1:
        raise ValueError("Mapo search response must contain one board index")
    response = responses[0]
    if not isinstance(response, dict) or response.get("error") or response.get("timed_out"):
        raise ValueError("Mapo search returned an error or timed out")
    if response.get("_shards", {}).get("failed", 0):
        raise ValueError("Mapo search returned partial results")
    hits = response.get("hits", {}).get("hits")
    if not isinstance(hits, list):
        raise ValueError("Mapo search hits missing")
    rows = []
    for hit in hits:
        row = hit.get("_source", {}) if isinstance(hit, dict) else {}
        title, published, link = (row.get(k) for k in ("ba_title", "ba_regdate", "link_url"))
        if not all(isinstance(value, str) and value.strip() for value in (title, published, link)):
            raise ValueError("Mapo search result lacks title, date or URL")
        assert isinstance(title, str) and isinstance(published, str) and isinstance(link, str)
        if _extract_date_from_text(published) is None:
            raise ValueError("Mapo search result has invalid registration date")
        parsed = urlparse(urljoin(list_url, link))
        base = urlparse(list_url)
        if (parsed.scheme, parsed.netloc) != (base.scheme, base.netloc):
            raise ValueError("Mapo search detail URL must remain on the configured host")
        if not re.fullmatch(r"/site/[^/]+/board/[^/]+/[1-9][0-9]*", parsed.path):
            raise ValueError("Mapo search result has unsupported detail URL")
        rows.append({
            "title": title.strip(), "date": published,
            "url": parsed._replace(query="", fragment="").geturl(),
        })
    return json.dumps(rows, ensure_ascii=False)
