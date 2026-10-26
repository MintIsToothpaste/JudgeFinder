from __future__ import annotations

from collections.abc import Mapping
from unittest.mock import Mock

import pytest
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
    monkeypatch: pytest.MonkeyPatch,
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


def test_requests_http_client_does_not_retry_non_handshake_ssl_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_requests_http_client_passes_verify_false_to_default_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_requests_http_client_preserves_verify_false_on_legacy_tls_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


@pytest.mark.parametrize("use_session", [False, True])
def test_missing_issuer_retries_with_verified_system_trust(
    monkeypatch: pytest.MonkeyPatch, use_session: bool,
) -> None:
    client = RequestsHttpClient()
    primary = Mock(side_effect=requests.exceptions.SSLError(
        "unable to get local issuer certificate",
    ))
    fallback = Mock(return_value=DummyResponse(text="verified"))
    monkeypatch.setattr(client._session if use_session else requests, "get", primary)
    monkeypatch.setattr(client._system_trust_session, "get", fallback)
    client._session.cookies.set("test_cookie", "public-session", domain="example.com")

    assert client.get_text("https://example.com", use_session=use_session) == "verified"
    assert primary.call_count == 1
    fallback.assert_called_once_with(
        "https://example.com", timeout=10.0, headers=None, verify=True,
    )
    if use_session:
        assert client._system_trust_session.cookies.get("test_cookie") == "public-session"


def test_system_verification_failure_is_not_bypassed(monkeypatch: pytest.MonkeyPatch) -> None:
    client = RequestsHttpClient()
    monkeypatch.setattr(requests, "get", Mock(side_effect=requests.exceptions.SSLError(
        "unable to verify the first certificate",
    )))
    fallback = Mock(side_effect=requests.exceptions.SSLError("certificate has expired"))
    insecure = Mock(side_effect=AssertionError("must not disable verification"))
    monkeypatch.setattr(client._system_trust_session, "get", fallback)
    monkeypatch.setattr(client._legacy_tls_insecure_session, "get", insecure)
    with pytest.raises(requests.exceptions.SSLError, match="expired"):
        client.get_text("https://example.com")
    assert fallback.call_args.kwargs["verify"] is True
    insecure.assert_not_called()


@pytest.mark.parametrize("message", ["certificate has expired", "hostname mismatch"])
def test_other_certificate_failures_do_not_use_system_fallback(
    monkeypatch: pytest.MonkeyPatch, message: str,
) -> None:
    client = RequestsHttpClient()
    monkeypatch.setattr(requests, "get", Mock(side_effect=requests.exceptions.SSLError(message)))
    fallback = Mock(side_effect=AssertionError("unexpected fallback"))
    monkeypatch.setattr(client._system_trust_session, "get", fallback)
    with pytest.raises(requests.exceptions.SSLError, match=message):
        client.get_text("https://example.com")
    fallback.assert_not_called()


@pytest.mark.parametrize("error,session_name", [
    ("unable to get local issuer certificate", "_system_trust_session"),
    ("[SSL: SSLV3_ALERT_HANDSHAKE_FAILURE]", "_legacy_tls_session"),
])
def test_post_preserves_method_body_and_tls_on_retry(
    monkeypatch: pytest.MonkeyPatch, error: str, session_name: str,
) -> None:
    client = RequestsHttpClient()
    primary = Mock(side_effect=requests.exceptions.SSLError(error))
    fallback = Mock(return_value=DummyResponse(text="verified"))
    monkeypatch.setattr(requests, "post", primary)
    monkeypatch.setattr(getattr(client, session_name), "post", fallback)
    body = b"keyword=%C6%F2%B0%A1%C0%A7%BF%F8"
    assert client.post_text("https://example.com/search", data=body) == "verified"
    assert primary.call_args == fallback.call_args
    assert fallback.call_args.kwargs["data"] == body
    assert fallback.call_args.kwargs["verify"] is True


def test_post_uses_session_and_raises_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    client = RequestsHttpClient()
    requester = Mock(return_value=DummyResponse(status_code=503))
    monkeypatch.setattr(client._session, "post", requester)
    with pytest.raises(requests.HTTPError):
        client.post_text("https://example.com/search", data=b"page=1", use_session=True)
    requester.assert_called_once_with(
        "https://example.com/search", data=b"page=1", timeout=10.0, headers=None, verify=True,
    )
