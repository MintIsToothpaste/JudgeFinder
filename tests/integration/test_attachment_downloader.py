from __future__ import annotations

import io
import json
import tempfile
import threading
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlparse

from judgefinder.adapters.attachments.downloader import download_notice_attachments
from judgefinder.interfaces.cli.download import main


def _hwpx() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/header.xml", '<head xmlns="urn:test"/>')
        archive.writestr("Contents/section0.xml", '<section xmlns="urn:test"/>')
    return buffer.getvalue()


HWPX = _hwpx()
# Signature fixture, not a complete editable HWP document.
HWP_SIGNATURE_FIXTURE = (
    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"HWP Document File\x00" + b"\x00" * 64
)
# Signature fixture; PDF parsing and rendering are outside the downloader's scope.
PDF_SIGNATURE_FIXTURE = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"


class AttachmentHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/notice")
            self.end_headers()
            return
        pages = {
            "/notice": '<li>신청서.hwpx <a href="/getFile">다운로드</a></li>',
            "/mixed": (
                '<a href="/getFile">신청서.hwpx</a>'
                '<a href="/bad">오류.hwp</a>'
                '<a href="javascript:customDownload(1)">미지원.hwp</a>'
                '<a href="/hwp">동의서.hwp</a>'
            ),
            "/large": '<a href="/too-large">대용량.hwp</a>',
            "/archive-notice": '<a href="/archive">서식모음.zip</a>',
            "/pdf-archive-notice": '<a href="/pdf-archive">공고모음.zip</a>',
            "/traversal": '<a href="/unsafe-name">신청서.hwpx</a>',
            "/empty": '<a href="/unused">안내.docx</a>',
            "/pdf-notice": (
                '<div>공고문.pdf <a href="/pdf-file">다운로드</a></div>'
                '<div>신청서.hwpx <a href="/getFile">다운로드</a></div>'
            ),
            "/fake-pdf-notice": '<a href="/fake-pdf">공고문.pdf</a>',
            "/truncated-pdf-notice": '<a href="/truncated-pdf">공고문.pdf</a>',
        }
        if path in pages:
            self.send_response(200)
            self.send_header("Set-Cookie", "notice_session=ready; Path=/")
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(pages[path].encode("utf-8"))
            return
        if path == "/getFile":
            if self.headers.get("Cookie") != "notice_session=ready" or not self.headers.get(
                "Referer", ""
            ).endswith(("/notice", "/mixed", "/pdf-notice")):
                self.send_error(403)
                return
            self._file(HWPX, "신청서.hwpx")
            return
        if path == "/hwp":
            self._file(HWP_SIGNATURE_FIXTURE, "동의서.hwp")
            return
        if path == "/pdf-file":
            self._file(PDF_SIGNATURE_FIXTURE, "공고문.pdf")
            return
        if path == "/fake-pdf":
            self._file(b"<html>Session expired</html>", "공고문.pdf")
            return
        if path == "/truncated-pdf":
            self._file(PDF_SIGNATURE_FIXTURE.split(b"%%EOF")[0], "공고문.pdf")
            return
        if path == "/unsafe-name":
            self._file(HWPX, "../../서식.hwpx")
            return
        if path == "/too-large":
            self._file(HWP_SIGNATURE_FIXTURE + b"x" * 4096, "대용량.hwp")
            return
        if path == "/bad":
            self._file(b"<html>Session expired</html>", "error.hwp")
            return
        if path in {"/archive", "/pdf-archive"}:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                if path == "/pdf-archive":
                    archive.writestr("forms/notice.PDF", PDF_SIGNATURE_FIXTURE)
                else:
                    archive.writestr("forms/form.hwp", HWP_SIGNATURE_FIXTURE)
            self._file(buffer.getvalue(), "forms.zip")
            return
        self.send_error(404)

    def _file(self, payload: bytes, filename: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(filename)}")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        pass


class AttachmentDownloaderTests(unittest.TestCase):
    server: ThreadingHTTPServer
    thread: threading.Thread
    base_url: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), AttachmentHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output_dir = Path(self.temporary.name)

    def test_downloads_binary_with_cookie_referer_and_korean_filename(self) -> None:
        report = download_notice_attachments(self.base_url + "/notice", output_dir=self.output_dir)
        self.assertTrue(report.ok, report.failures)
        self.assertEqual(len(report.files), 1)
        record = report.files[0]
        self.assertEqual(record.original_name, "신청서.hwpx")
        self.assertEqual((report.directory / record.filename).read_bytes(), HWPX)
        manifest = json.loads((report.directory / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["ok"])
        self.assertEqual(manifest["files"][0]["sha256"], record.sha256)

    def test_repeated_download_reuses_file(self) -> None:
        url = self.base_url + "/notice"
        first = download_notice_attachments(url, output_dir=self.output_dir)
        second = download_notice_attachments(url, output_dir=self.output_dir)
        self.assertTrue(second.ok)
        self.assertEqual(first.files[0].filename, second.files[0].filename)
        self.assertEqual(second.files[0].status, "existing")
        self.assertEqual(len(list(second.directory.glob("*.hwpx"))), 1)
        self.assertEqual(list(second.directory.glob("*.part")), [])

    def test_preserves_successes_when_other_attachments_fail(self) -> None:
        report = download_notice_attachments(self.base_url + "/mixed", output_dir=self.output_dir)
        self.assertFalse(report.ok)
        self.assertEqual(len(report.files), 2)
        self.assertEqual(len(report.failures), 1)
        self.assertEqual(len(report.unsupported), 1)
        self.assertIn("possibly an HTML error page", report.failures[0].reason)
        self.assertEqual(list(report.directory.glob("*.part")), [])

    def test_size_limit_removes_partial_download(self) -> None:
        report = download_notice_attachments(
            self.base_url + "/large", output_dir=self.output_dir, max_file_bytes=100
        )
        self.assertFalse(report.ok)
        self.assertEqual(report.files, [])
        self.assertIn("size limit", report.failures[0].reason)
        self.assertEqual([p.name for p in report.directory.iterdir()], ["manifest.json"])

    def test_zip_with_hwp_is_saved_without_extracting(self) -> None:
        report = download_notice_attachments(
            self.base_url + "/archive-notice", output_dir=self.output_dir
        )
        self.assertTrue(report.ok)
        self.assertTrue(report.files[0].filename.endswith(".zip"))
        self.assertFalse((report.directory / "forms").exists())

    def test_downloads_pdf_with_hwpx_and_reuses_both_files(self) -> None:
        url = self.base_url + "/pdf-notice"
        first = download_notice_attachments(url, output_dir=self.output_dir)
        self.assertTrue(first.ok, first.failures)
        self.assertEqual(len(first.files), 2)
        pdf = next(record for record in first.files if record.filename.endswith(".pdf"))
        self.assertEqual(pdf.original_name, "공고문.pdf")
        self.assertEqual((first.directory / pdf.filename).read_bytes(), PDF_SIGNATURE_FIXTURE)
        manifest = json.loads((first.directory / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["files"]), 2)
        second = download_notice_attachments(url, output_dir=self.output_dir)
        self.assertTrue(second.ok, second.failures)
        self.assertTrue(all(record.status == "existing" for record in second.files))
        self.assertEqual(len(list(second.directory.glob("*.pdf"))), 1)

    def test_rejects_html_disguised_as_pdf(self) -> None:
        report = download_notice_attachments(
            self.base_url + "/fake-pdf-notice", output_dir=self.output_dir
        )
        self.assertFalse(report.ok)
        self.assertEqual(report.files, [])
        self.assertIn("possibly an HTML error page", report.failures[0].reason)
        self.assertEqual(list(report.directory.glob("*.part")), [])
        self.assertEqual(list(report.directory.glob("*.pdf")), [])

    def test_rejects_truncated_pdf(self) -> None:
        report = download_notice_attachments(
            self.base_url + "/truncated-pdf-notice", output_dir=self.output_dir
        )
        self.assertFalse(report.ok)
        self.assertEqual(report.files, [])
        self.assertIn("possibly truncated", report.failures[0].reason)
        self.assertEqual(list(report.directory.glob("*.part")), [])

    def test_zip_containing_only_pdf_is_saved_without_extracting(self) -> None:
        report = download_notice_attachments(
            self.base_url + "/pdf-archive-notice", output_dir=self.output_dir
        )
        self.assertTrue(report.ok, report.failures)
        self.assertTrue(report.files[0].filename.endswith(".zip"))
        self.assertFalse((report.directory / "forms").exists())

    def test_filename_cannot_escape_notice_directory(self) -> None:
        report = download_notice_attachments(
            self.base_url + "/traversal", output_dir=self.output_dir
        )
        self.assertTrue(report.ok)
        self.assertEqual((report.directory / report.files[0].filename).parent, report.directory)
        self.assertNotIn("/", report.files[0].filename)
        self.assertNotIn("\\", report.files[0].filename)

    def test_modified_existing_file_is_not_overwritten(self) -> None:
        url = self.base_url + "/notice"
        first = download_notice_attachments(url, output_dir=self.output_dir)
        destination = first.directory / first.files[0].filename
        destination.write_bytes(b"local modification")
        second = download_notice_attachments(url, output_dir=self.output_dir)
        self.assertFalse(second.ok)
        self.assertIn("different contents", second.failures[0].reason)
        self.assertEqual(destination.read_bytes(), b"local modification")

    def test_no_supported_files_is_an_explicit_failure(self) -> None:
        report = download_notice_attachments(self.base_url + "/empty", output_dir=self.output_dir)
        self.assertFalse(report.ok)
        self.assertIn("No HWP/HWPX/PDF/ZIP", report.failures[0].reason)

    def test_notice_http_error_is_recorded(self) -> None:
        report = download_notice_attachments(self.base_url + "/missing", output_dir=self.output_dir)
        self.assertFalse(report.ok)
        self.assertEqual(len(report.failures), 1)
        self.assertTrue((report.directory / "manifest.json").is_file())

    def test_uses_final_detail_url_as_referer(self) -> None:
        report = download_notice_attachments(
            self.base_url + "/redirect", output_dir=self.output_dir
        )
        self.assertTrue(report.ok, report.failures)
        self.assertEqual(report.resolved_notice_url, self.base_url + "/notice")

    def test_cli_reads_utf8_bom_file_and_deduplicates_urls(self) -> None:
        urls_file = self.output_dir / "urls.txt"
        url = self.base_url + "/notice"
        urls_file.write_text(f"# comment\n{url}\n\n{url}\n", encoding="utf-8-sig")
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            exit_code = main(
                [url, "--urls-file", str(urls_file), "--output-dir", str(self.output_dir)]
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(stdout.getvalue().splitlines()), 1)

    def test_cli_reports_failure_and_continues_to_next_notice(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(
                [
                    self.base_url + "/missing",
                    self.base_url + "/notice",
                    "--output-dir",
                    str(self.output_dir),
                ]
            )
        self.assertEqual(exit_code, 1)
        self.assertIn("ERROR", stderr.getvalue())
        self.assertEqual(len(stdout.getvalue().splitlines()), 1)

    def test_rejects_non_http_input(self) -> None:
        with self.assertRaises(ValueError):
            download_notice_attachments("file:///private.hwp", output_dir=self.output_dir)


if __name__ == "__main__":
    unittest.main()
