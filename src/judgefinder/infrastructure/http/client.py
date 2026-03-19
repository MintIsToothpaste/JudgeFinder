from __future__ import annotations

import logging
import ssl
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

import requests
from requests.adapters import HTTPAdapter
from urllib3.exceptions import InsecureRequestWarning
from urllib3.poolmanager import PoolManager

LOGGER = logging.getLogger(__name__)


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
        verify_tls: bool = True,
    ) -> str:
        ...

    def get_response(
        self,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
        verify_tls: bool = True,
    ) -> HttpResponse:
        ...


class _LegacyTlsHttpAdapter(HTTPAdapter):
    def __init__(self, *, allow_insecure: bool = False) -> None:
        self._allow_insecure = allow_insecure
        super().__init__()

    def init_poolmanager(self, *args: object, **kwargs: object) -> None:
        ssl_context = ssl.create_default_context()
        ssl_context.set_ciphers("DEFAULT:@SECLEVEL=1")
        if self._allow_insecure:
            ssl_context.check_hostname = False
        kwargs["ssl_context"] = ssl_context
        self.poolmanager = PoolManager(*args, **kwargs)


class RequestsHttpClient(HttpClient):
    def __init__(self) -> None:
        self._session = requests.Session()
        self._legacy_tls_session = requests.Session()
        self._legacy_tls_session.mount("https://", _LegacyTlsHttpAdapter())
        self._legacy_tls_insecure_session = requests.Session()
        self._legacy_tls_insecure_session.mount(
            "https://",
            _LegacyTlsHttpAdapter(allow_insecure=True),
        )

    def get_text(
        self,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
        use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        response = self._request(
            url=url,
            timeout_seconds=timeout_seconds,
            headers=headers,
            use_session=use_session,
            verify_tls=verify_tls,
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
        verify_tls: bool = True,
    ) -> HttpResponse:
        response = self._request(
            url=url,
            timeout_seconds=timeout_seconds,
            headers=headers,
            use_session=use_session,
            verify_tls=verify_tls,
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
        verify_tls: bool,
    ) -> requests.Response:
        requester = self._session.get if use_session else requests.get
        try:
            return _perform_request(
                requester,
                url=url,
                timeout_seconds=timeout_seconds,
                headers=headers,
                verify_tls=verify_tls,
            )
        except requests.exceptions.SSLError as exc:
            if not _should_retry_with_legacy_tls(url=url, exc=exc):
                raise

            LOGGER.debug("Retrying %s with legacy TLS compatibility mode.", url)
            legacy_requester = (
                self._legacy_tls_session.get
                if verify_tls
                else self._legacy_tls_insecure_session.get
            )
            return _perform_request(
                legacy_requester,
                url=url,
                timeout_seconds=timeout_seconds,
                headers=headers,
                verify_tls=verify_tls,
            )


def _perform_request(
    requester,
    *,
    url: str,
    timeout_seconds: float,
    headers: Mapping[str, str] | None,
    verify_tls: bool,
) -> requests.Response:
    if verify_tls:
        return requester(url, timeout=timeout_seconds, headers=headers, verify=True)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", InsecureRequestWarning)
        return requester(url, timeout=timeout_seconds, headers=headers, verify=False)


def _should_retry_with_legacy_tls(*, url: str, exc: requests.exceptions.SSLError) -> bool:
    if not url.lower().startswith("https://"):
        return False
    message = str(exc).lower()
    return (
        "handshake failure" in message
        or "handshake_failure" in message
        or "sslv3 alert" in message
    )
