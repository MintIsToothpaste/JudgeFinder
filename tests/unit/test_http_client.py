from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from judgefinder.infrastructure.http import windows_curl
from judgefinder.infrastructure.http.client import RequestsHttpClient
from judgefinder.infrastructure.http.windows_curl import WindowsCurlHttpClient


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
    monkeypatch: pytest.MonkeyPatch,
    use_session: bool,
) -> None:
    client = RequestsHttpClient()
    primary = Mock(
        side_effect=requests.exceptions.SSLError(
            "unable to get local issuer certificate",
        )
    )
    fallback = Mock(return_value=DummyResponse(text="verified"))
    monkeypatch.setattr(client._session if use_session else requests, "get", primary)
    monkeypatch.setattr(client._system_trust_session, "get", fallback)
    client._session.cookies.set("test_cookie", "public-session", domain="example.com")

    assert client.get_text("https://example.com", use_session=use_session) == "verified"
    assert primary.call_count == 1
    fallback.assert_called_once_with(
        "https://example.com",
        timeout=10.0,
        headers=None,
        verify=True,
    )
    if use_session:
        assert client._system_trust_session.cookies.get("test_cookie") == "public-session"


def test_system_verification_failure_is_not_bypassed(monkeypatch: pytest.MonkeyPatch) -> None:
    client = RequestsHttpClient()
    monkeypatch.setattr(
        requests,
        "get",
        Mock(
            side_effect=requests.exceptions.SSLError(
                "unable to verify the first certificate",
            )
        ),
    )
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
    monkeypatch: pytest.MonkeyPatch,
    message: str,
) -> None:
    client = RequestsHttpClient()
    monkeypatch.setattr(requests, "get", Mock(side_effect=requests.exceptions.SSLError(message)))
    fallback = Mock(side_effect=AssertionError("unexpected fallback"))
    monkeypatch.setattr(client._system_trust_session, "get", fallback)
    with pytest.raises(requests.exceptions.SSLError, match=message):
        client.get_text("https://example.com")
    fallback.assert_not_called()


@pytest.mark.parametrize(
    "error,session_name",
    [
        ("unable to get local issuer certificate", "_system_trust_session"),
        ("[SSL: SSLV3_ALERT_HANDSHAKE_FAILURE]", "_legacy_tls_session"),
    ],
)
def test_post_preserves_method_body_and_tls_on_retry(
    monkeypatch: pytest.MonkeyPatch,
    error: str,
    session_name: str,
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
        "https://example.com/search",
        data=b"page=1",
        timeout=10.0,
        headers=None,
        verify=True,
    )


@pytest.mark.parametrize("operation", ["get_text", "get_response", "post_text"])
@pytest.mark.parametrize(
    ("content_type", "markup", "wire_encoding", "initial_encoding"),
    [
        ("text/html", '<meta charset="utf-8">경기도', "utf-8", "ISO-8859-1"),
        ("text/html", '<meta charset="euc-kr">공고', "euc-kr", "ISO-8859-1"),
        (
            "text/html",
            '<meta http-equiv="Content-Type" content="text/html; charset=cp949">공고',
            "cp949",
            "ISO-8859-1",
        ),
        ("text/html; charset=cp949", '<meta charset="utf-8">공고', "cp949", "cp949"),
        ("application/json", '{"제목":"공고"}', "utf-8", "utf-8"),
        (
            "application/xml",
            '<?xml version="1.0" encoding="euc-kr"?><rss>공고</rss>',
            "euc-kr",
            None,
        ),
        ("text/html", "공고", "utf-8", "ISO-8859-1"),
        ("text/html; charset=not-an-encoding", "공고", "utf-8", "not-an-encoding"),
    ],
)
def test_http_decodes_declared_charset_or_utf8_fallback(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    content_type: str,
    markup: str,
    wire_encoding: str,
    initial_encoding: str | None,
) -> None:
    response = requests.Response()
    response.status_code = 200
    response.url = "https://example.com/list"
    response.headers["Content-Type"] = content_type
    response._content = markup.encode(wire_encoding)
    response.encoding = initial_encoding
    client = RequestsHttpClient()
    monkeypatch.setattr(client, "_request", lambda **kwargs: response)
    if operation == "post_text":
        result = client.post_text(response.url, data=b"page=1")
    elif operation == "get_response":
        result = client.get_response(response.url).text
    else:
        result = client.get_text(response.url)
    assert result == markup


def _curl_wire(body: bytes = b"ok", status: int = 200) -> bytes:
    metadata = {"http_code": status, "url_effective": "https://example.com/final",
                "ssl_verify_result": 0}
    headers = {"content-type": ["text/html"], "x-test": ["one", "two"]}
    return (body + windows_curl._METADATA_MARKER
            + json.dumps(metadata).encode() + b"\n" + json.dumps(headers).encode())


def _mock_windows_client(
    monkeypatch: pytest.MonkeyPatch, *, body: bytes = b"ok", status: int = 200,
) -> tuple[WindowsCurlHttpClient, Mock]:
    client = WindowsCurlHttpClient()
    client._executable = "curl.exe"
    run = Mock(return_value=subprocess.CompletedProcess(
        [], 0, stdout=_curl_wire(body, status), stderr=b"",
    ))
    monkeypatch.setattr(windows_curl.subprocess, "run", run)
    return client, run


@pytest.mark.parametrize("body,expected", [
    ('<meta charset="utf-8">평가위원'.encode(), '<meta charset="utf-8">평가위원'),
    ('<meta charset="cp949">공고'.encode("cp949"), '<meta charset="cp949">공고'),
    (b"body" + windows_curl._METADATA_MARKER + b"inside", "body"
     + windows_curl._METADATA_MARKER.decode() + "inside"),
])
def test_windows_curl_preserves_body_headers_encoding_and_verified_https(
    monkeypatch: pytest.MonkeyPatch, body: bytes, expected: str,
) -> None:
    client, run = _mock_windows_client(monkeypatch, body=body)
    response = client.get_response(
        "https://example.com/list", headers={"User-Agent": "JudgeFinder"},
    )
    assert response.status_code == 200 and response.text == expected
    assert response.url == "https://example.com/final"
    assert response.headers["x-test"] == "one, two"
    command = run.call_args.args[0]
    assert command[:2] == ["curl.exe", "--disable"]
    assert command[command.index("--proto") + 1] == "=https"
    assert command[command.index("--proto-redir") + 1] == "=https"
    assert command[command.index("--header") + 1] == "User-Agent: JudgeFinder"
    assert not {"--insecure", "-k", "--ssl-no-revoke", "--cookie"} & set(command)
    assert run.call_args.kwargs["timeout"] == 12.0


def test_windows_curl_reuses_only_requested_session_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, run = _mock_windows_client(monkeypatch)
    try:
        for _ in range(2):
            assert client.get_text("https://example.com", use_session=True) == "ok"
        commands = [call.args[0] for call in run.call_args_list]
        jars = [cmd[cmd.index("--cookie-jar") + 1] for cmd in commands]
        assert jars[0] == jars[1]
        directory = Path(jars[0]).parent
        assert directory.exists()
        assert all(cmd[cmd.index("--cookie") + 1] == jars[0] for cmd in commands)
        client.get_text("https://example.com", use_session=False)
        assert "--cookie-jar" not in run.call_args.args[0]
    finally:
        client.close()
    assert not directory.exists()


def test_windows_curl_get_response_exposes_http_error_but_text_methods_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, run = _mock_windows_client(monkeypatch, status=403)
    assert client.get_response("https://example.com").status_code == 403
    with pytest.raises(requests.HTTPError):
        client.get_text("https://example.com")
    with pytest.raises(requests.HTTPError):
        client.post_text("https://example.com", data=b"search=value")
    command = run.call_args.args[0]
    assert command[command.index("--data-binary") + 1] == "@-"
    assert run.call_args.kwargs["input"] == b"search=value"


@pytest.mark.parametrize("code,error", [
    (28, requests.Timeout), (60, requests.exceptions.SSLError),
    (35, requests.exceptions.SSLError), (7, requests.ConnectionError),
])
def test_windows_curl_propagates_transport_failures(
    monkeypatch: pytest.MonkeyPatch, code: int, error: type[Exception],
) -> None:
    client, run = _mock_windows_client(monkeypatch)
    run.return_value = subprocess.CompletedProcess([], code, stdout=b"", stderr=b"failed")
    with pytest.raises(error, match="failed"):
        client.get_text("https://example.com")


def test_windows_curl_kills_timed_out_process_and_reports_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, run = _mock_windows_client(monkeypatch)
    run.side_effect = subprocess.TimeoutExpired("curl.exe", 3)
    with pytest.raises(requests.Timeout, match="timed out"):
        client.get_text("https://example.com", timeout_seconds=1)


@pytest.mark.parametrize("url,options", [
    ("http://example.com", {}), ("https://user:password@example.com", {}),
    ("https://example.com", {"verify_tls": False}),
    ("https://example.com", {"timeout_seconds": float("inf")}),
    ("https://example.com", {"headers": {"X-Test": "value\r\nOther: injected"}}),
])
def test_windows_curl_rejects_invalid_requests_before_starting_process(
    monkeypatch: pytest.MonkeyPatch, url: str, options: dict,
) -> None:
    client, run = _mock_windows_client(monkeypatch)
    with pytest.raises(ValueError):
        client.get_text(url, **options)
    run.assert_not_called()


@pytest.mark.parametrize("wire", [b"no metadata", b"body" + windows_curl._METADATA_MARKER + b"bad"])
def test_windows_curl_never_accepts_missing_or_broken_response_metadata(
    monkeypatch: pytest.MonkeyPatch, wire: bytes,
) -> None:
    client, run = _mock_windows_client(monkeypatch)
    run.return_value = subprocess.CompletedProcess([], 0, stdout=wire, stderr=b"")
    with pytest.raises(requests.RequestException, match="metadata"):
        client.get_text("https://example.com")


@pytest.mark.parametrize("version,accepted", [
    (b"curl 8.21.0 (Windows) Schannel", True),
    (b"curl 8.21.0 (Windows) OpenSSL", False),
    (b"curl 7.82.0 (Windows) Schannel", False),
])
def test_windows_curl_checks_backend_and_version_once_per_client(
    monkeypatch: pytest.MonkeyPatch, version: bytes, accepted: bool,
) -> None:
    client = WindowsCurlHttpClient()
    monkeypatch.setattr(windows_curl, "_windows_curl_executable", lambda: Path("curl.exe"))
    run = Mock(side_effect=[
        subprocess.CompletedProcess([], 0, stdout=version, stderr=b""),
        subprocess.CompletedProcess([], 0, stdout=_curl_wire(), stderr=b""),
        subprocess.CompletedProcess([], 0, stdout=_curl_wire(), stderr=b""),
    ])
    monkeypatch.setattr(windows_curl.subprocess, "run", run)
    if accepted:
        assert client.get_text("https://example.com") == "ok"
        assert client.get_text("https://example.com") == "ok"
        assert run.call_count == 3
    else:
        with pytest.raises(RuntimeError, match="Schannel"):
            client.get_text("https://example.com")
        assert run.call_count == 1


def test_windows_curl_reports_unsupported_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(windows_curl, "sys", SimpleNamespace(platform="linux"))
    with pytest.raises(RuntimeError, match="requires Windows"):
        WindowsCurlHttpClient().get_text("https://example.com")
