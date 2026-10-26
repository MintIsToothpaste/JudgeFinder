from __future__ import annotations

import codecs
import logging
import re
import ssl
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import requests
import truststore
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


@runtime_checkable
class FormHttpClient(Protocol):
    """Optional capability for read-only board search forms."""

    def post_text(
        self, url: str, *, data: bytes, timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None, use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        ...


class _LegacyTlsHttpAdapter(HTTPAdapter):
    def __init__(self, *, allow_insecure: bool = False) -> None:
        self._allow_insecure = allow_insecure
        super().__init__()

    def init_poolmanager(
        self, connections: int, maxsize: int, block: bool = False, **pool_kwargs: Any,
    ) -> None:
        ssl_context = ssl.create_default_context()
        ssl_context.set_ciphers("DEFAULT:@SECLEVEL=1")
        if self._allow_insecure:
            ssl_context.check_hostname = False
        pool_kwargs["ssl_context"] = ssl_context
        self.poolmanager = PoolManager(
            num_pools=connections, maxsize=maxsize, block=block, **pool_kwargs,
        )


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
        self._system_trust_session = requests.Session()
        self._system_trust_session.mount("https://", _SystemTrustHttpAdapter())

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
        _set_response_encoding(response)
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
        _set_response_encoding(response)
        return HttpResponse(
            status_code=response.status_code,
            text=response.text,
            headers=dict(response.headers),
            url=response.url,
        )

    def post_text(
        self, url: str, *, data: bytes, timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None, use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        response = self._request(
            url=url, timeout_seconds=timeout_seconds, headers=headers,
            use_session=use_session, verify_tls=verify_tls, method="post", data=data,
        )
        response.raise_for_status()
        _set_response_encoding(response)
        return response.text

    def _request(
        self,
        *,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None,
        use_session: bool,
        verify_tls: bool,
        method: str = "get",
        data: bytes | None = None,
    ) -> requests.Response:
        requester = getattr(self._session if use_session else requests, method)
        try:
            return _perform_request(
                requester,
                url=url,
                timeout_seconds=timeout_seconds,
                headers=headers,
                verify_tls=verify_tls,
                data=data,
            )
        except requests.exceptions.SSLError as exc:
            if verify_tls and _is_missing_issuer_error(url, exc):
                LOGGER.debug("Retrying %s with system certificate verification.", url)
                if use_session:
                    self._system_trust_session.cookies.update(self._session.cookies)
                response = _perform_request(
                    getattr(self._system_trust_session, method), url=url,
                    timeout_seconds=timeout_seconds, headers=headers, verify_tls=True,
                    data=data,
                )
                if use_session:
                    self._session.cookies.update(self._system_trust_session.cookies)
                return response
            if not _should_retry_with_legacy_tls(url=url, exc=exc):
                raise

            LOGGER.debug("Retrying %s with legacy TLS compatibility mode.", url)
            legacy_session = (
                self._legacy_tls_session
                if verify_tls
                else self._legacy_tls_insecure_session
            )
            return _perform_request(
                getattr(legacy_session, method),
                url=url,
                timeout_seconds=timeout_seconds,
                headers=headers,
                verify_tls=verify_tls,
                data=data,
            )


def _set_response_encoding(response: requests.Response) -> None:
    # Requests supplies Latin-1 for charset-less HTML, even when its meta says UTF-8.
    content_type = response.headers.get("Content-Type", "")
    declared = re.search(r"charset\s*=\s*['\"]?([^\s;'\"]+)", content_type, re.I)
    encoding = declared.group(1) if declared else None
    if not encoding:
        prefix = getattr(response, "content", b"")[:8192]
        if isinstance(prefix, bytes):
            markup = prefix.decode("ascii", errors="ignore")
            meta = re.search(r"<meta\b[^>]*charset\s*=\s*['\"]?([\w.-]+)", markup, re.I)
            xml = re.search(r"<\?xml\b[^>]*encoding\s*=\s*['\"]([\w.-]+)", markup, re.I)
            encoding = meta.group(1) if meta else xml.group(1) if xml else None
        if not encoding:
            current = response.encoding
            encoding = current if current and current.lower() != "iso-8859-1" else "utf-8"
    try:
        codecs.lookup(encoding)
    except LookupError:
        encoding = "utf-8"
    response.encoding = encoding


class _SystemTrustHttpAdapter(HTTPAdapter):
    def init_poolmanager(
        self, connections: int, maxsize: int, block: bool = False, **pool_kwargs: Any,
    ) -> None:
        pool_kwargs["ssl_context"] = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.poolmanager = PoolManager(
            num_pools=connections, maxsize=maxsize, block=block, **pool_kwargs,
        )


def _is_missing_issuer_error(url: str, exc: requests.exceptions.SSLError) -> bool:
    return url.lower().startswith("https://") and any(
        marker in str(exc).lower()
        for marker in (
            "unable to get local issuer certificate", "unable to verify the first certificate",
        )
    )


def _perform_request(
    requester: Callable[..., requests.Response],
    *,
    url: str,
    timeout_seconds: float,
    headers: Mapping[str, str] | None,
    verify_tls: bool,
    data: bytes | None = None,
) -> requests.Response:
    extra = {"data": data} if data is not None else {}
    if verify_tls:
        return requester(url, timeout=timeout_seconds, headers=headers, verify=True, **extra)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", InsecureRequestWarning)
        return requester(url, timeout=timeout_seconds, headers=headers, verify=False, **extra)


def _should_retry_with_legacy_tls(*, url: str, exc: requests.exceptions.SSLError) -> bool:
    if not url.lower().startswith("https://"):
        return False
    message = str(exc).lower()
    return (
        "handshake failure" in message
        or "handshake_failure" in message
        or "sslv3 alert" in message
    )
