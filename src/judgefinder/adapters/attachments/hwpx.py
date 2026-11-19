from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from io import BytesIO
from urllib.parse import urlparse
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

import requests

from judgefinder.adapters.attachments.downloader import _read_limited
from judgefinder.adapters.attachments.parser import extract_attachment_links

_MAX_BYTES = 2 * 1024 * 1024
_MAX_FILES = 3
_SECTION = re.compile(r"Contents/section[0-9]+\.xml")
_TEXT_TAG = "{http://www.hancom.co.kr/hwpml/2011/paragraph}t"


def official_hwpx_texts(
    html: str, page_url: str, *, timeout_seconds: float,
    request_headers: Mapping[str, str] | None = None,
) -> Iterable[str]:
    page = urlparse(page_url)
    if page.scheme != "https":
        return
    files = 0
    for link in extract_attachment_links(html, page_url=page_url).links:
        if not link.filename.lower().endswith(".hwpx"):
            continue
        target = urlparse(link.url)
        if (target.scheme, target.netloc.lower()) != (page.scheme, page.netloc.lower()):
            continue
        files += 1
        try:
            text = ""
            with requests.get(
                link.url, headers={**(request_headers or {}), "Referer": page_url},
                timeout=min(timeout_seconds, 10.0),
                stream=True, allow_redirects=False,
            ) as response:
                if response.status_code == 200:
                    text = _extract_hwpx_text(_read_limited(response, _MAX_BYTES))
            if text:
                yield text
        except (requests.RequestException, BadZipFile, ElementTree.ParseError,
                OSError, ValueError, RuntimeError):
            # An inaccessible or unsupported attachment leaves the notice unconfirmed.
            pass
        if files >= _MAX_FILES:
            return


def _extract_hwpx_text(payload: bytes) -> str:
    parts: list[str] = []
    with ZipFile(BytesIO(payload)) as archive:
        sections = [entry for entry in archive.infolist() if _SECTION.fullmatch(entry.filename)]
        if sum(entry.file_size for entry in sections) > _MAX_BYTES:
            raise ValueError("HWPX sections exceed the text size limit")
        for entry in sections:
            with archive.open(entry) as section:
                xml = section.read().decode("utf-8-sig")
            if "<!DOCTYPE" in xml or "<!ENTITY" in xml:
                raise ValueError("HWPX document type declarations are unsupported")
            root = ElementTree.fromstring(xml)
            parts.extend(node.text or "" for node in root.iter(_TEXT_TAG))
    return " ".join(parts)
