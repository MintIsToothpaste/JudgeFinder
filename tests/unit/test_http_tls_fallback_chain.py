from __future__ import annotations

import ssl
from unittest.mock import Mock

import pytest
import requests

from judgefinder.infrastructure.http.client import RequestsHttpClient


@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize("use_session", [False, True])
@pytest.mark.parametrize("first,second,intermediate", [
    ("[SSL: SSLV3_ALERT_HANDSHAKE_FAILURE]", "unable to get local issuer certificate",
     "_legacy_tls_session"),
    ("unable to get local issuer certificate", "[SSL: SSLV3_ALERT_HANDSHAKE_FAILURE]",
     "_system_trust_session"),
    ("[SSL: SSLV3_ALERT_HANDSHAKE_FAILURE]", "[SSL: SSLV3_ALERT_HANDSHAKE_FAILURE]",
     "_legacy_tls_session"),
])
def test_combined_verified_fallback_preserves_request_and_session(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    use_session: bool,
    first: str,
    second: str,
    intermediate: str,
) -> None:
    client = RequestsHttpClient()
    url = "https://example.test/notices"
    primary = Mock(side_effect=requests.exceptions.SSLError(first))
    middle = Mock(side_effect=requests.exceptions.SSLError(second))
    response = requests.Response()
    response.status_code = 200
    response._content = b"verified"
    response.url = url
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    client._session.cookies.set("public_session", "existing", domain="example.test")

    def verified(*args: object, **kwargs: object) -> requests.Response:
        assert kwargs["verify"] is True
        if use_session:
            assert client._system_trust_legacy_session.cookies.get("public_session") == "existing"
            client._system_trust_legacy_session.cookies.set(
                "next_public_session", "updated", domain="example.test",
            )
        return response

    combined = Mock(side_effect=verified)
    monkeypatch.setattr(client._session if use_session else requests, method, primary)
    monkeypatch.setattr(getattr(client, intermediate), method, middle)
    monkeypatch.setattr(client._system_trust_legacy_session, method, combined)
    headers = {"Referer": "https://example.test/"}
    if method == "get":
        actual = client.get_text(url, headers=headers, use_session=use_session)
    else:
        actual = client.post_text(
            url, data=b"query=public", headers=headers, use_session=use_session,
        )
    assert actual == "verified"
    assert primary.call_count == middle.call_count == combined.call_count == 1
    assert primary.call_args == middle.call_args == combined.call_args
    if use_session:
        assert client._session.cookies.get("next_public_session") == "updated"


@pytest.mark.parametrize("first,intermediate", [
    ("unable to get local issuer certificate", "_system_trust_session"),
    ("[SSL: SSLV3_ALERT_HANDSHAKE_FAILURE]", "_legacy_tls_session"),
])
@pytest.mark.parametrize("failure", ["certificate has expired", "hostname mismatch"])
def test_invalid_peer_certificate_never_uses_combined_fallback(
    monkeypatch: pytest.MonkeyPatch, first: str, intermediate: str, failure: str,
) -> None:
    client = RequestsHttpClient()
    monkeypatch.setattr(requests, "get", Mock(side_effect=requests.exceptions.SSLError(first)))
    secondary = Mock(side_effect=requests.exceptions.SSLError(failure))
    monkeypatch.setattr(getattr(client, intermediate), "get", secondary)
    combined = Mock(side_effect=AssertionError("invalid certificates must not be retried"))
    monkeypatch.setattr(client._system_trust_legacy_session, "get", combined)
    with pytest.raises(requests.exceptions.SSLError, match=failure):
        client.get_text("https://example.test/notices")
    combined.assert_not_called()


def test_combined_context_keeps_certificate_and_hostname_verification() -> None:
    client = RequestsHttpClient()
    adapter = client._system_trust_legacy_session.get_adapter("https://example.test/")
    assert isinstance(adapter, requests.adapters.HTTPAdapter)
    context = adapter.poolmanager.connection_pool_kw["ssl_context"]
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname


@pytest.mark.parametrize("failure", [
    "unable to get local issuer certificate", "[SSL: SSLV3_ALERT_HANDSHAKE_FAILURE]",
])
def test_http_redirect_retries_only_when_failure_has_a_real_https_request(
    monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    client = RequestsHttpClient()
    request = requests.Request("GET", "https://example.test/notices").prepare()
    error = requests.exceptions.SSLError(failure, request=request)
    monkeypatch.setattr(requests, "get", Mock(side_effect=error))
    response = requests.Response()
    response.status_code = 200
    response._content = b"verified"
    assert request.url is not None
    response.url = request.url
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    session = client._system_trust_session if "issuer" in failure else client._legacy_tls_session
    retry = Mock(return_value=response)
    monkeypatch.setattr(session, "get", retry)
    assert client.get_text("http://example.test/notices") == "verified"
    assert retry.call_args.kwargs["verify"] is True


def test_http_without_https_failure_evidence_never_uses_tls_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = RequestsHttpClient()
    error = requests.exceptions.SSLError("unable to get local issuer certificate")
    monkeypatch.setattr(requests, "get", Mock(side_effect=error))
    retry = Mock()
    monkeypatch.setattr(client._system_trust_session, "get", retry)
    with pytest.raises(requests.exceptions.SSLError):
        client.get_text("http://example.test/notices")
    retry.assert_not_called()
