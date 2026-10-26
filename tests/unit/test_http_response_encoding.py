from __future__ import annotations

import pytest
import requests

from judgefinder.infrastructure.http.client import RequestsHttpClient


@pytest.mark.parametrize("operation", ["get_text", "get_response", "post_text"])
@pytest.mark.parametrize(
    ("content_type", "markup", "wire_encoding", "initial_encoding"),
    [
        ("text/html", '<meta charset="utf-8">경기도', "utf-8", "ISO-8859-1"),
        ("text/html", '<meta charset="euc-kr">공고', "euc-kr", "ISO-8859-1"),
        ("text/html", '<meta http-equiv="Content-Type" content="text/html; '
         'charset=cp949">공고', "cp949", "ISO-8859-1"),
        ("text/html; charset=cp949", '<meta charset="utf-8">공고', "cp949", "cp949"),
        ("application/json", '{"제목":"공고"}', "utf-8", "utf-8"),
        ("application/xml", '<?xml version="1.0" encoding="euc-kr"?><rss>공고</rss>',
         "euc-kr", None),
        ("text/html", "공고", "utf-8", "ISO-8859-1"),
        ("text/html; charset=not-an-encoding", "공고", "utf-8", "not-an-encoding"),
    ],
)
def test_http_decodes_declared_charset_or_utf8_fallback(
    monkeypatch: pytest.MonkeyPatch, operation: str, content_type: str,
    markup: str, wire_encoding: str, initial_encoding: str | None,
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
