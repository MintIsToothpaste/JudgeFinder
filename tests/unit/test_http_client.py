from __future__ import annotations

from collections.abc import Mapping

import requests

from judgefinder.infrastructure.http.client import RequestsHttpClient


class DummyResponse:
    def __init__(self, text: str = "ok", status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code
        self.headers: dict[str, str] = {}
        self.url = "https://example.com"
        self.encoding: str | None = None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status={self.status_code}")


def test_requests_http_client_retries_with_legacy_tls_on_handshake_failure(
    monkeypatch,
) -> None:
    client = RequestsHttpClient()
    calls: list[str] = []

    def fail(
        url: str,
        timeout: float,
        headers: Mapping[str, str] | None = None,
        verify: bool = True,
    ) -> DummyResponse:
        _ = url
        _ = timeout
        _ = headers
        _ = verify
        calls.append("default")
        raise requests.exceptions.SSLError("[SSL: SSLV3_ALERT_HANDSHAKE_FAILURE]")

    def succeed(
        url: str,
        timeout: float,
        headers: Mapping[str, str] | None = None,
        verify: bool = True,
    ) -> DummyResponse:
        _ = url
        _ = timeout
        _ = headers
        _ = verify
        calls.append("legacy")
        return DummyResponse(text="legacy-ok")

    monkeypatch.setattr(requests, "get", fail)
    monkeypatch.setattr(client._legacy_tls_session, "get", succeed)

    assert client.get_text("https://example.com") == "legacy-ok"
    assert calls == ["default", "legacy"]


def test_requests_http_client_does_not_retry_non_handshake_ssl_errors(monkeypatch) -> None:
    client = RequestsHttpClient()

    def fail(
        url: str,
        timeout: float,
        headers: Mapping[str, str] | None = None,
        verify: bool = True,
    ) -> DummyResponse:
        _ = url
        _ = timeout
        _ = headers
        _ = verify
        raise requests.exceptions.SSLError("certificate verify failed")

    monkeypatch.setattr(requests, "get", fail)

    try:
        client.get_text("https://example.com")
    except requests.exceptions.SSLError as exc:
        assert "certificate verify failed" in str(exc)
    else:  # pragma: no cover - defensive branch
        raise AssertionError("Expected SSLError to be raised.")


def test_requests_http_client_passes_verify_false_to_default_request(monkeypatch) -> None:
    client = RequestsHttpClient()
    observed: list[bool] = []

    def succeed(
        url: str,
        timeout: float,
        headers: Mapping[str, str] | None = None,
        verify: bool = True,
    ) -> DummyResponse:
        _ = url
        _ = timeout
        _ = headers
        observed.append(verify)
        return DummyResponse(text="ok")

    monkeypatch.setattr(requests, "get", succeed)

    assert client.get_text("https://example.com", verify_tls=False) == "ok"
    assert observed == [False]


def test_requests_http_client_preserves_verify_false_on_legacy_tls_retry(monkeypatch) -> None:
    client = RequestsHttpClient()
    observed: list[tuple[str, bool]] = []

    def fail(
        url: str,
        timeout: float,
        headers: Mapping[str, str] | None = None,
        verify: bool = True,
    ) -> DummyResponse:
        _ = url
        _ = timeout
        _ = headers
        observed.append(("default", verify))
        raise requests.exceptions.SSLError("[SSL: SSLV3_ALERT_HANDSHAKE_FAILURE]")

    def succeed(
        url: str,
        timeout: float,
        headers: Mapping[str, str] | None = None,
        verify: bool = True,
    ) -> DummyResponse:
        _ = url
        _ = timeout
        _ = headers
        observed.append(("legacy", verify))
        return DummyResponse(text="legacy-ok")

    monkeypatch.setattr(requests, "get", fail)
    monkeypatch.setattr(client._legacy_tls_insecure_session, "get", succeed)

    assert client.get_text("https://example.com", verify_tls=False) == "legacy-ok"
    assert observed == [("default", False), ("legacy", False)]
