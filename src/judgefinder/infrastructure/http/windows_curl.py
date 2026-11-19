from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

import requests

from judgefinder.infrastructure.http.client import HttpResponse, _set_response_encoding

_METADATA_MARKER = b"\n__JUDGEFINDER_CURL_METADATA__\n"


def _windows_curl_executable() -> Path:
    if sys.platform != "win32":
        raise RuntimeError("windows_curl transport requires Windows and Schannel curl >= 7.83")
    executable = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "curl.exe"
    if not executable.is_file():
        raise RuntimeError("Windows system curl.exe was not found")
    return executable


class WindowsCurlHttpClient:
    """Opt-in HTTPS transport using the Windows system TLS policy and certificate store."""

    def __init__(self) -> None:
        self._executable: str | None = None
        self._session_directory: tempfile.TemporaryDirectory[str] | None = None

    def close(self) -> None:
        if self._session_directory is not None:
            self._session_directory.cleanup()
            self._session_directory = None

    def get_text(
        self, url: str, timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None, use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        response = self._request(url, timeout_seconds, headers, use_session, verify_tls)
        response.raise_for_status()
        return response.text

    def get_response(
        self, url: str, timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None, use_session: bool = False,
        verify_tls: bool = True,
    ) -> HttpResponse:
        response = self._request(url, timeout_seconds, headers, use_session, verify_tls)
        return HttpResponse(
            status_code=response.status_code, text=response.text,
            headers=dict(response.headers), url=response.url,
        )

    def post_text(
        self, url: str, *, data: bytes, timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None, use_session: bool = False,
        verify_tls: bool = True,
    ) -> str:
        response = self._request(url, timeout_seconds, headers, use_session, verify_tls, data)
        response.raise_for_status()
        return response.text

    def _get_executable(self) -> str:
        if self._executable is None:
            executable = str(_windows_curl_executable())
            try:
                result = subprocess.run(
                    [executable, "--disable", "--version"], capture_output=True,
                    timeout=5, check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise RuntimeError("Unable to run Windows system curl.exe") from exc
            version = result.stdout.decode("utf-8", errors="replace")
            match = re.match(r"curl ([0-9]+)\.([0-9]+)\.([0-9]+)", version)
            if (result.returncode or "Schannel" not in version or match is None
                or tuple(map(int, match.groups())) < (7, 83, 0)):
                raise RuntimeError("windows_curl transport requires Schannel curl >= 7.83")
            self._executable = executable
        return self._executable

    def _request(
        self, url: str, timeout_seconds: float, headers: Mapping[str, str] | None,
        use_session: bool, verify_tls: bool, data: bytes | None = None,
    ) -> requests.Response:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("windows_curl transport requires an HTTPS URL without credentials")
        if not verify_tls:
            raise ValueError("windows_curl transport always verifies TLS certificates")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        command = [
            self._get_executable(), "--disable", "--silent", "--show-error", "--globoff",
            "--location", "--max-redirs", "5", "--proto", "=https", "--proto-redir", "=https",
            "--compressed", "--max-time", str(timeout_seconds),
            "--write-out", _METADATA_MARKER.decode("ascii") + "%{json}\n%{header_json}",
        ]
        for key, value in (headers or {}).items():
            if not key or ":" in key or any(c in key + value for c in "\r\n"):
                raise ValueError("Invalid HTTP header")
            command.extend(["--header", f"{key}: {value}"])
        if use_session:
            if self._session_directory is None:
                self._session_directory = tempfile.TemporaryDirectory(prefix="judgefinder-curl-")
            cookies = str(Path(self._session_directory.name) / "cookies.txt")
            command.extend(["--cookie", cookies, "--cookie-jar", cookies])
        if data is not None:
            command.extend(["--data-binary", "@-"])
        command.extend(["--url", requests.utils.requote_uri(url)])
        try:
            result = subprocess.run(
                command, input=data, capture_output=True, timeout=timeout_seconds + 2, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as exc:
            raise requests.Timeout(f"Windows curl timed out requesting {url}") from exc
        except OSError as exc:
            raise requests.ConnectionError("Unable to start Windows curl") from exc
        if result.returncode:
            message = result.stderr.decode("utf-8", errors="replace").strip()
            if result.returncode == 28:
                raise requests.Timeout(message)
            if result.returncode in {35, 51, 58, 60, 77, 83, 90, 91}:
                raise requests.exceptions.SSLError(message)
            raise requests.ConnectionError(f"Windows curl failed ({result.returncode}): {message}")
        body, marker, trailer = result.stdout.rpartition(_METADATA_MARKER)
        try:
            if not marker:
                raise ValueError("Response metadata missing")
            text = trailer.decode("utf-8").lstrip()
            metadata, position = json.JSONDecoder().raw_decode(text)
            response_headers = json.loads(text[position:].lstrip())
            status = metadata["http_code"]
            effective_url = metadata["url_effective"]
            if (type(status) is not int or not 100 <= status <= 599
                or not isinstance(effective_url, str)
                or urlparse(effective_url).scheme != "https"
                or not isinstance(response_headers, dict)
                or not all(isinstance(k, str) and isinstance(v, list)
                           and all(isinstance(item, str) for item in v)
                           for k, v in response_headers.items())):
                raise ValueError("Invalid response metadata")
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise requests.RequestException("Invalid Windows curl response metadata") from exc
        if metadata.get("ssl_verify_result", 0) not in {0, "0"}:
            raise requests.exceptions.SSLError("Windows curl certificate verification failed")
        response = requests.Response()
        response.status_code = status
        response.url = effective_url
        response.headers.update(
            {key: ", ".join(values) for key, values in response_headers.items()},
        )
        response._content = body
        _set_response_encoding(response)
        return response
