from __future__ import annotations

import unittest

from judgefinder.adapters.attachments.parser import extract_attachment_links


class AttachmentParserTests(unittest.TestCase):
    def test_resolves_pdf_and_hwp_downloads_and_skips_preview(self) -> None:
        discovery = extract_attachment_links(
            """
            <ul>
              <li>공고문.pdf
                <a href="/preview?id=1">미리보기</a>
                <a href="/getFile?id=1">다운로드</a>
              </li>
              <li>등록 신청서.hwp
                <a href="/preview?id=2">미리보기</a>
                <a href="/getFile?id=2">다운로드</a>
              </li>
            </ul>
            """,
            page_url="https://city.go.kr/notices/123",
        )
        self.assertEqual(len(discovery.links), 2)
        self.assertEqual(discovery.links[0].url, "https://city.go.kr/getFile?id=1")
        self.assertEqual(discovery.links[0].filename, "공고문.pdf")
        self.assertEqual(discovery.links[1].url, "https://city.go.kr/getFile?id=2")
        self.assertEqual(discovery.links[1].filename, "등록 신청서.hwp")

    def test_standard_egov_call_preserves_declared_context_path(self) -> None:
        discovery = extract_attachment_links(
            """
            <script>
              function fn_egov_downFile(id, sn) {
                window.open('/portal/cmm/fms/FileDown.do?atchFileId='+id+'&fileSn='+sn);
              }
            </script>
            <a href="javascript:fn_egov_downFile('FILE_123', '0')">신청서.hwp</a>
            """,
            page_url="https://city.go.kr/portal/notice.do",
        )
        self.assertEqual(
            discovery.links[0].url,
            "https://city.go.kr/portal/cmm/fms/FileDown.do?atchFileId=FILE_123&fileSn=0",
        )

    def test_nested_div_attachment_groups_keep_pdf_and_hwp_separate(self) -> None:
        discovery = extract_attachment_links(
            """
            <li><div class="file-preview-down-group-wrap">
              <div class="file-preview-down-group">
                <span class="file-name">공고문.pdf</span>
                <a href="/getFile?fileNo=1"><span>다운로드</span></a>
              </div>
              <div class="file-preview-down-group">
                <span class="file-name">제출서류.hwp</span>
                <a href="/notice/list">목록</a>
                <a href="/getFile?fileNo=2"><span>다운로드</span></a>
              </div>
            </div></li>
            """,
            page_url="https://city.go.kr/notice/123",
        )
        self.assertEqual(len(discovery.links), 2)
        self.assertEqual(discovery.links[0].url, "https://city.go.kr/getFile?fileNo=1")
        self.assertEqual(discovery.links[0].filename, "공고문.pdf")
        self.assertEqual(discovery.links[1].url, "https://city.go.kr/getFile?fileNo=2")
        self.assertEqual(discovery.links[1].filename, "제출서류.hwp")

    def test_finds_uppercase_pdf_link_without_download_label(self) -> None:
        discovery = extract_attachment_links(
            '<a href="/files/NOTICE.PDF">공고문</a><a href="/files/photo.jpg">사진</a>',
            page_url="https://city.go.kr/notice/123",
        )
        self.assertEqual(len(discovery.links), 1)
        self.assertEqual(discovery.links[0].url, "https://city.go.kr/files/NOTICE.PDF")

    def test_uses_base_url_and_deduplicates_links(self) -> None:
        discovery = extract_attachment_links(
            """
            <base href="/files/">
            <a href="form.hwpx">등록신청서.hwpx</a>
            <a href="form.hwpx" download>다운로드</a>
            <a href="mailto:test@example.com">메일</a>
            """,
            page_url="https://city.go.kr/notice/123",
        )
        self.assertEqual(len(discovery.links), 1)
        self.assertEqual(discovery.links[0].url, "https://city.go.kr/files/form.hwpx")

    def test_extracts_explicit_url_from_button(self) -> None:
        discovery = extract_attachment_links(
            """<button onclick="location.href='/fileDown.do?id=3'">서식.hwp</button>""",
            page_url="https://city.go.kr/notice",
        )
        self.assertEqual(discovery.links[0].url, "https://city.go.kr/fileDown.do?id=3")

    def test_reports_unknown_javascript_without_executing_it(self) -> None:
        discovery = extract_attachment_links(
            """<a href="#" onclick="customDownload('secret')">신청서.hwp</a>""",
            page_url="https://city.go.kr/notice",
        )
        self.assertEqual(discovery.links, [])
        self.assertEqual(len(discovery.unsupported), 1)
        self.assertIn("customDownload", discovery.unsupported[0])

    def test_does_not_assign_one_filename_to_several_files(self) -> None:
        discovery = extract_attachment_links(
            """
            <div>
              신청서.hwp <a href="/getFile?id=1">다운로드</a>
              동의서.hwpx <a href="/getFile?id=2">다운로드</a>
            </div>
            """,
            page_url="https://city.go.kr/notice",
        )
        self.assertEqual(len(discovery.links), 2)
        self.assertTrue(all(not link.filename for link in discovery.links))


if __name__ == "__main__":
    unittest.main()
