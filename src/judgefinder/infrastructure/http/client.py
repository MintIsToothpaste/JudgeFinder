from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

import requests


@dataclass(slots=True)
class HttpResponse:
    status_code: int
    text: str
    headers: Mapping[str, str]
    url: str

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class HttpClient(Protocol):
    def get_text(
        self,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
    ) -> str:
        ...

    def get_response(
        self,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
    ) -> HttpResponse:
        ...


class RequestsHttpClient(HttpClient):
    def __init__(self) -> None:
        self._session = requests.Session()

    def get_text(
        self,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
    ) -> str:
        response = self._request(
            url=url,
            timeout_seconds=timeout_seconds,
            headers=headers,
            use_session=use_session,
        )
        response.raise_for_status()
        response.encoding = response.encoding or "utf-8"
        return response.text

    def get_response(
        self,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
    ) -> HttpResponse:
        response = self._request(
            url=url,
            timeout_seconds=timeout_seconds,
            headers=headers,
            use_session=use_session,
        )
        response.encoding = response.encoding or "utf-8"
        return HttpResponse(
            status_code=response.status_code,
            text=response.text,
            headers=dict(response.headers),
            url=response.url,
        )

    def _request(
        self,
        *,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None,
        use_session: bool,
    ) -> requests.Response:
        requester = self._session.get if use_session else requests.get
        return requester(url, timeout=timeout_seconds, headers=headers)
