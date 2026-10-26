from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

SUPPORTED_SUFFIXES = {".hwp", ".hwpx", ".pdf", ".zip"}
FILE_NAME = re.compile(
    r"([^\r\n<>/\\]+?\.(?:hwpx?|zip|pdf|docx?|xlsx?|pptx?|png|jpe?g))\b", re.IGNORECASE
)
PREVIEW = re.compile(r"미리보기|바로보기|preview|viewer|synap|docview", re.IGNORECASE)
DOWNLOAD = re.compile(
    r"getfile|filedown|downfile|download|다운로드|내려받기|파일받기", re.IGNORECASE
)
QUOTED_URL = re.compile(r"['\"]((?:https?://|/|\./|\.\./)[^'\"\s]+)['\"]")
EGOV_CALL = re.compile(
    r"fn_egov_downFile\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)",
    re.IGNORECASE,
)
EGOV_PATH = re.compile(r"['\"]([^'\"\s]*?/cmm/fms/FileDown\.do(?:;[^?'\"]+)?)\?")


@dataclass(frozen=True, slots=True)
class AttachmentLink:
    url: str
    filename: str = ""


@dataclass(slots=True)
class AttachmentDiscovery:
    links: list[AttachmentLink] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)


def extract_attachment_links(payload: str | bytes, *, page_url: str) -> AttachmentDiscovery:
    soup = BeautifulSoup(payload, "html.parser")
    base = soup.find("base", href=True)
    base_url = urljoin(page_url, str(base["href"])) if base else page_url
    script_text = "\n".join(script.get_text() for script in soup.find_all("script"))
    egov_path_match = EGOV_PATH.search(script_text)
    egov_path = egov_path_match.group(1) if egov_path_match else "/cmm/fms/FileDown.do"
    result = AttachmentDiscovery()
    seen: set[str] = set()

    for element in soup.find_all(["a", "button"]):
        label = element.get_text(" ", strip=True)
        action = " ".join(str(element.get(key, "")) for key in ("href", "onclick"))
        hints = " ".join(
            (
                label,
                str(element.get("title", "")),
                str(element.get("aria-label", "")),
                str(element.get("class", "")),
                action,
            )
        )
        if PREVIEW.search(hints):
            continue

        filename = _attachment_filename(element)
        if filename and not _supported_name(filename):
            continue
        egov_call = EGOV_CALL.search(action)
        raw_url = _direct_url(element)
        if egov_call:
            query = urlencode({"atchFileId": egov_call.group(1), "fileSn": egov_call.group(2)})
            raw_url = f"{egov_path}?{query}"
        if not filename and not DOWNLOAD.search(hints) and not egov_call:
            continue
        if not raw_url:
            if filename or DOWNLOAD.search(hints):
                description = f"Unsupported attachment action: {filename or label}: {action}"
                if description not in result.unsupported:
                    result.unsupported.append(description)
            continue

        url = urljoin(base_url, raw_url)
        if urlparse(url).scheme not in {"http", "https"}:
            continue
        if url not in seen:
            seen.add(url)
            result.links.append(AttachmentLink(url=url, filename=filename))

    return result


def _direct_url(element: Tag) -> str:
    for attribute in ("data-href", "data-url", "href"):
        value = element.get(attribute)
        if isinstance(value, str) and value.strip():
            value = value.strip()
            if not value.startswith("#") and not value.lower().startswith("javascript:"):
                return value
    action = " ".join(str(element.get(key, "")) for key in ("onclick", "href"))
    match = QUOTED_URL.search(action)
    return match.group(1) if match else ""


def _attachment_filename(element: Tag) -> str:
    for text in (
        element.get_text("\n", strip=True),
        str(element.get("download", "")),
        str(element.get("title", "")),
    ):
        match = FILE_NAME.search(text)
        if match:
            return match.group(1).strip()
    raw_url = _direct_url(element)
    parsed = urlparse(raw_url)
    for value in (unquote(parsed.path.rsplit("/", 1)[-1]), *parse_qs(parsed.query).values()):
        text = value if isinstance(value, str) else value[0]
        match = FILE_NAME.search(unquote(text))
        if match:
            return match.group(1).strip()
    hints = " ".join(
        (
            element.get_text(" ", strip=True),
            raw_url,
            str(element.get("class", "")),
            str(element.get("title", "")),
            str(element.get("aria-label", "")),
        )
    )
    if not DOWNLOAD.search(hints):
        return ""
    container = element.find_parent(["li", "tr", "dd", "p", "div"]) or element.parent
    if container is not None:
        # Only use a shared filename when this container describes one file.
        names = list(FILE_NAME.finditer(container.get_text("\n", strip=True)))
        if len(names) == 1:
            return names[0].group(1).strip()
    return ""


def _supported_name(filename: str) -> bool:
    return any(filename.lower().endswith(suffix) for suffix in SUPPORTED_SUFFIXES)
