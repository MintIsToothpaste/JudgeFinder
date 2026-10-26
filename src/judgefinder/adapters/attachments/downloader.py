from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import zipfile
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from email.message import Message
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from judgefinder.adapters.attachments.parser import AttachmentLink, extract_attachment_links

OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
MAX_PAGE_BYTES = 5 * 1024 * 1024


@dataclass(slots=True)
class DownloadedAttachment:
    attachment_url: str
    resolved_url: str
    original_name: str
    filename: str
    sha256: str
    size_bytes: int
    status: str


@dataclass(slots=True)
class DownloadFailure:
    url: str
    reason: str


@dataclass(slots=True)
class DownloadReport:
    notice_url: str
    directory: Path
    resolved_notice_url: str = ""
    files: list[DownloadedAttachment] = field(default_factory=list)
    failures: list[DownloadFailure] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.files) and not self.failures and not self.unsupported


def download_notice_attachments(
    notice_url: str,
    *,
    output_dir: Path,
    timeout_seconds: float = 30.0,
    max_file_bytes: int = 50 * 1024 * 1024,
) -> DownloadReport:
    parsed = urlparse(notice_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Notice URL must be an absolute HTTP(S) URL.")
    if timeout_seconds <= 0 or max_file_bytes <= 0:
        raise ValueError("Timeout and maximum file size must be positive.")
    notice_key = hashlib.sha256(notice_url.encode("utf-8")).hexdigest()[:16]
    directory = output_dir.resolve() / notice_key
    directory.mkdir(parents=True, exist_ok=True)
    report = DownloadReport(notice_url=notice_url, directory=directory)

    with requests.Session() as session:
        session.headers["User-Agent"] = "Mozilla/5.0 (compatible; JudgeFinder/0.1)"
        retries = Retry(
            total=2,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
        )
        session.mount("https://", HTTPAdapter(max_retries=retries))
        session.mount("http://", HTTPAdapter(max_retries=retries))
        try:
            with session.get(notice_url, timeout=timeout_seconds, stream=True) as response:
                response.raise_for_status()
                payload = _read_limited(response, MAX_PAGE_BYTES)
                report.resolved_notice_url = response.url
            discovery = extract_attachment_links(payload, page_url=report.resolved_notice_url)
            report.unsupported = discovery.unsupported
            for link in discovery.links:
                try:
                    report.files.append(
                        _download_file(
                            session,
                            link,
                            directory=directory,
                            referer=report.resolved_notice_url,
                            timeout_seconds=timeout_seconds,
                            max_file_bytes=max_file_bytes,
                        )
                    )
                except (requests.RequestException, ValueError, OSError) as exc:
                    report.failures.append(DownloadFailure(link.url, str(exc)))
            if not discovery.links and not discovery.unsupported:
                report.failures.append(
                    DownloadFailure(notice_url, "No HWP/HWPX/PDF/ZIP download links found.")
                )
        except (requests.RequestException, ValueError, OSError) as exc:
            report.failures.append(DownloadFailure(notice_url, str(exc)))

    _write_manifest(report)
    return report


def _read_limited(response: requests.Response, limit: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_content(64 * 1024):
        size += len(chunk)
        if size > limit:
            raise ValueError(f"Response exceeds size limit ({limit} bytes).")
        chunks.append(chunk)
    return b"".join(chunks)


def _download_file(
    session: requests.Session,
    link: AttachmentLink,
    *,
    directory: Path,
    referer: str,
    timeout_seconds: float,
    max_file_bytes: int,
) -> DownloadedAttachment:
    temporary_path: Path | None = None
    try:
        with session.get(
            link.url,
            headers={"Referer": referer},
            timeout=timeout_seconds,
            stream=True,
        ) as response:
            response.raise_for_status()
            original_name = (
                _response_filename(response)
                or link.filename
                or unquote(urlparse(response.url).path.rsplit("/", 1)[-1])
                or "attachment"
            )
            digest = hashlib.sha256()
            size = 0
            with tempfile.NamedTemporaryFile(dir=directory, suffix=".part", delete=False) as file:
                temporary_path = Path(file.name)
                for chunk in response.iter_content(64 * 1024):
                    size += len(chunk)
                    if size > max_file_bytes:
                        raise ValueError(f"Attachment exceeds size limit ({max_file_bytes} bytes).")
                    digest.update(chunk)
                    file.write(chunk)

            suffix = _detect_document_type(temporary_path)
            filename = f"{digest.hexdigest()[:16]}_{_safe_filename(original_name, suffix)}"
            destination = directory / filename
            status = "downloaded"
            if destination.exists():
                if hashlib.sha256(destination.read_bytes()).hexdigest() != digest.hexdigest():
                    raise ValueError(f"Existing file has different contents: {filename}")
                status = "existing"
            else:
                temporary_path.replace(destination)
            return DownloadedAttachment(
                attachment_url=link.url,
                resolved_url=response.url,
                original_name=original_name,
                filename=filename,
                sha256=digest.hexdigest(),
                size_bytes=size,
                status=status,
            )
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _response_filename(response: requests.Response) -> str:
    message = Message()
    message["Content-Disposition"] = response.headers.get("Content-Disposition", "")
    filename = message.get_filename() or ""
    with suppress(UnicodeEncodeError, UnicodeDecodeError):
        filename = filename.encode("latin-1").decode("utf-8")
    return unquote(filename)


def _safe_filename(name: str, suffix: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    stem = Path(name).stem[:96].rstrip(" .") or "attachment"
    if re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", stem, re.IGNORECASE):
        stem = f"_{stem}"
    return stem + suffix


def _detect_document_type(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith(b"%PDF-"):
        if b"%%EOF" not in data[-1024:]:
            raise ValueError("PDF is missing its end-of-file marker (possibly truncated).")
        return ".pdf"
    if data.startswith(OLE_SIGNATURE) and b"HWP Document File\x00" in data:
        return ".hwp"
    if not zipfile.is_zipfile(path):
        raise ValueError(
            "Response is not an HWP, HWPX, PDF, or ZIP file (possibly an HTML error page)."
        )
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if "mimetype" in names and "Contents/header.xml" in names:
                with archive.open("mimetype") as mime:
                    mimetype = mime.read(128).strip()
                if mimetype == b"application/hwp+zip" and any(
                    re.fullmatch(r"Contents/section\d+\.xml", name) for name in names
                ):
                    return ".hwpx"
            if any(name.lower().endswith((".hwp", ".hwpx", ".pdf")) for name in names):
                return ".zip"
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise ValueError(f"Cannot inspect attachment archive: {exc}") from exc
    raise ValueError("ZIP does not contain an HWP/HWPX/PDF document.")


def _write_manifest(report: DownloadReport) -> None:
    manifest = {
        "notice_url": report.notice_url,
        "resolved_notice_url": report.resolved_notice_url,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "ok": report.ok,
        "files": [asdict(file) for file in report.files],
        "failures": [asdict(failure) for failure in report.failures],
        "unsupported": report.unsupported,
    }
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=report.directory, suffix=".part", delete=False
        ) as file:
            temporary_path = Path(file.name)
            json.dump(manifest, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary_path, report.directory / "manifest.json")
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
