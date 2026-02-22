from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

import requests


class HttpClient(Protocol):
    def get_text(
        self,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        ...


class RequestsHttpClient(HttpClient):
    def get_text(
        self,
        url: str,
        timeout_seconds: float = 10.0,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        response = requests.get(url, timeout=timeout_seconds, headers=headers)
        response.raise_for_status()
        response.encoding = response.encoding or "utf-8"
        return response.text
