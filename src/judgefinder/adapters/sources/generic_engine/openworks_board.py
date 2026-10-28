from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource


class OpenworksBoardSource(GenericEngineSource):
    """Follow the public OpenWorks board's session-bound pagination form."""

    def _load_page(self, *, page_index: int) -> str:
        if self.fixture_path is not None or page_index in self.page_cache:
            return super()._load_page(page_index=page_index)
        if not self.use_session:
            raise ValueError("OpenWorks pagination requires a session")
        if page_index == 1:
            # A bare board URL opens normally; explicit paging requires its form token.
            payload = self._request_text(self.list_url)
        else:
            previous = self.page_cache.get(page_index - 1)
            if previous is None:
                raise ValueError("OpenWorks pagination requires the preceding page")
            tokens = BeautifulSoup(previous, "html5lib").select('input[name="csrfToken"]')
            if len(tokens) != 1 or not tokens[0].get("value"):
                raise ValueError("OpenWorks pagination form token missing or ambiguous")
            parsed = urlparse(self._build_request_url(page_index=page_index))
            query = parse_qs(parsed.query, keep_blank_values=True)
            query["csrfToken"] = [str(tokens[0]["value"])]
            query["q_rowPerPage"] = [str(self.html_profile.page_size if self.html_profile else 10)]
            payload = self._request_text(urlunparse(parsed._replace(
                query=urlencode(query, doseq=True),
            )))
        self.page_cache[page_index] = payload
        return payload
