from __future__ import annotations

import re
from datetime import date
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from bs4 import BeautifulSoup

from judgefinder.adapters.sources.generic_engine.source import GenericEngineSource
from judgefinder.domain.entities import Notice

# Public form values must stay in the POST body, never in the persisted reference URL.
FORM_FIELDS = {
    "g_secure", "g_ipaddr", "g_accountyear", "g_prg_id", "g_basis_path", "state",
    "page", "tpage", "stype", "a_dsply", "notice_no", "notice_year", "notice_kind",
    "cntrc_gub_cd", "cntrc_status", "skeyword",
}


class WonkwangContractSource(GenericEngineSource):
    """Read the anonymous contract board using its ordinary session-bound forms."""

    def __post_init__(self) -> None:
        super().__post_init__()
        self._form: dict[str, str] = {}
        self._last_page = 0

    def fetch(self, target_date: date) -> list[Notice]:
        if not self.use_session:
            raise ValueError("Wonkwang public contract forms require a session")
        return super().fetch(target_date)

    def _remember_form(self, payload: str, *, listing_page: int | None = None) -> None:
        soup = BeautifulSoup(payload, "html5lib")
        forms = soup.select("form#frm")
        if len(forms) != 1:
            raise ValueError("Wonkwang public contract form missing or ambiguous")
        values: dict[str, str] = {}
        for field in forms[0].select("input[name],select[name]"):
            name = str(field["name"])
            if name not in FORM_FIELDS:
                continue
            if name in values:
                raise ValueError("Wonkwang public contract form fields are ambiguous")
            if field.name == "select":
                selected = field.select_one("option[selected]") or field.select_one("option")
                values[name] = str(selected.get("value", "")) if selected else ""
            else:
                values[name] = str(field.get("value", ""))
        if not all(values.get(k) for k in ("g_secure", "g_accountyear", "g_prg_id")):
            raise ValueError("Wonkwang public contract form context missing")
        if listing_page is not None:
            if values.get("page") != str(listing_page):
                raise ValueError("Wonkwang public contract page differs from requested page")
            total = values.get("tpage", "")
            if not re.fullmatch(r"[0-9]+", total):
                raise ValueError("Wonkwang public contract total pages missing or invalid")
            self._last_page = max(1, int(total))
        self._form.update(values)

    def _post_form(self, endpoint: str, updates: dict[str, str]) -> str:
        payload = self._request_text(
            endpoint + "?" + urlencode({**self._form, **updates}), post=True,
        )
        self._remember_form(payload)
        return payload

    def _load_page(self, *, page_index: int) -> str:
        if self.fixture_path is not None or page_index in self.page_cache:
            return super()._load_page(page_index=page_index)
        if not self._form:
            self._remember_form(self._request_text(self.list_url))
        payload = self._post_form(self.list_url, {
            "page": str(page_index), "stype": "1", "notice_no": "",
            "skeyword": self.search_keyword,
        })
        self._remember_form(payload, listing_page=page_index)
        self.page_cache[page_index] = payload
        return payload

    def _is_last_page(self, page_index: int) -> bool:
        return bool(self._last_page and page_index >= self._last_page)

    def _load_detail(self, url: str) -> str:
        if url not in self.detail_cache:
            endpoint = urljoin(self.list_url, "cntrc_read.jsp")
            supplied, expected = urlparse(url), urlparse(endpoint)
            values = parse_qs(supplied.query)
            identifier = values.get("notice_no", [])
            if (supplied._replace(query="") != expected or set(values) != {"notice_no"}
                    or len(identifier) != 1 or not re.fullmatch(r"[a-fA-F0-9]{32}", identifier[0])):
                raise ValueError("Wonkwang detail must reference a configured official notice")
            if not self._form:
                self._remember_form(self._request_text(self.list_url))
            payload = self._post_form(endpoint, {"notice_no": identifier[0]})
            # A shell with HTTP 200 does not prove that the requested record was loaded.
            if self._form.get("notice_no") != identifier[0]:
                raise ValueError("Wonkwang detail does not confirm the requested notice ID")
            self.detail_cache[url] = payload
        return self.detail_cache[url]
