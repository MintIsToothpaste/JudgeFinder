# 공고 첨부파일 다운로드

공고 상세 페이지 URL에서 HWP·HWPX·PDF 파일과 해당 문서가 포함된 ZIP 파일을 내려받습니다.
기존 공고 수집기, 소스 설정, SQLite DB를 사용하거나 변경하지 않는 독립 명령입니다.
자동 서류 작성은 포함하지 않습니다.

## 실행

프로젝트 루트에서 기존 의존성을 설치한 뒤 실행합니다. 추가 패키지는 필요 없습니다.

```powershell
python -m pip install -e .
python -m judgefinder.interfaces.cli.download "https://지자체사이트/공고상세주소"
```

여러 공고 URL을 인자로 전달하거나, 기존 수집기의 출력을 UTF-8 파일로 저장해 전달할 수 있습니다.
수집기 명령은 기존 설정 파일이 준비된 환경에서 실행합니다.

```powershell
judgefinder collect --date today | Out-File -Encoding utf8 notices.txt
python -m judgefinder.interfaces.cli.download --urls-file notices.txt
```

URL 파일은 한 줄에 공고 상세 페이지 URL 하나를 작성합니다. UTF-8 BOM, 빈 줄,
`#`으로 시작하는 주석을 지원하며 중복 URL은 한 번만 처리합니다.

```powershell
python -m judgefinder.interfaces.cli.download --urls-file notices.txt `
  --output-dir data/attachments --timeout 30 --max-size-mb 50
```

- 기본 저장 위치: `data/attachments/<공고 URL의 SHA-256 앞 16자리>/`
- 파일명: `<파일 SHA-256 앞 16자리>_<안전하게 정리한 원본 파일명>`
- 표준 출력: 저장된 파일의 절대 경로, 한 줄에 하나
- 표준 오류: 실패·미지원 링크 및 `manifest.json` 경로
- 종료 코드: 모든 공고가 성공하면 `0`, 일부 실패·미지원·대상 파일 없음은 `1`
- URL 파일이나 실행 옵션 오류는 종료 코드 `2`

## 지원 범위

- `.hwp`, `.hwpx`, `.pdf`, `.zip` 링크 및 확장자가 없는 다운로드 엔드포인트
- 첨부파일명 옆에 별도 다운로드 링크가 있는 구조
- 상대 URL, HTML `base`, `data-href`/`data-url`
- 버튼의 JavaScript에 명시된 HTTP(S)·루트 상대·점 상대 URL
- 표준 `fn_egov_downFile('첨부ID', '파일순번')` 호출
  - 페이지 스크립트에 선언된 `/.../cmm/fms/FileDown.do` 경로를 우선 사용
  - 경로 선언이 없으면 표준 `/cmm/fms/FileDown.do` 사용
- 같은 세션의 쿠키 유지, 최종 상세 페이지 URL을 Referer로 전달
- 일시적인 연결 실패 및 HTTP 429/일부 5xx 응답에 최대 두 번 재시도

미리보기 링크와 이미지·Word·Excel 등 지원 대상이 아닌 형식은 제외합니다.
공고문과 제출서식을 구분해 선별하지 않고, 지원 형식에 해당하는 첨부파일을 모두 받습니다.
일반 JavaScript 실행, POST 폼, iframe 내부의 별도 첨부목록, 로그인·CAPTCHA·WAF 대응은
아직 지원하지 않습니다. 이를 요구하는 사이트는 추가 어댑터가 필요합니다.
첨부 링크를 찾지 못하거나 지원하지 않는 액션을 발견하면 성공으로 처리하지 않고 기록합니다.
기존 수집기의 지자체별 요청 전략과 TLS 호환 설정은 자동으로 상속하지 않습니다.

## 검증과 다운로드 기록

파일은 바이너리로 스트리밍 저장하며 기본 상한은 파일당 50 MiB입니다.
HTML 오류 페이지가 문서 이름으로 저장되지 않도록 다음 형식을 확인합니다.

- HWP 5.x: OLE 시그니처와 `HWP Document File` 헤더 문자열
- HWPX: ZIP 구조, `application/hwp+zip` mimetype, header/section 항목
- PDF: 파일 시작의 `%PDF-` 시그니처와 마지막 1,024바이트 내 `%%EOF` 종료 마커
- ZIP: HWP/HWPX/PDF 확장자의 파일 항목이 있는지 확인, 자동 압축 해제는 하지 않음

이는 컨테이너·시그니처 검증이며, 한글 프로그램이나 PDF 뷰어에서 문서가 정상적으로
열리는지까지 검증하지 않습니다. PDF 텍스트 추출·OCR 및 ZIP 내부 문서 검증은 하지 않습니다.
다운로드 도중 실패하거나 크기 제한을 초과하면 임시 파일을 제거합니다.

같은 공고를 재실행하면 파일을 다시 요청해 변경 여부를 확인하고, 같은 내용은 기존 파일을
재사용합니다. 내용이 바뀐 파일은 다른 해시 이름으로 저장합니다. 기존 파일의 내용이
수정되어 있다면 덮어쓰지 않고 오류를 기록합니다.

공고별 `manifest.json`에는 원본·최종 URL, 원본 파일명, 로컬 파일명, SHA-256, 크기,
다운로드 상태, 실패·미지원 사유를 기록합니다. 이 파일은 가장 최근 실행 결과로 교체되며
과거 실행 이력 전체를 보관하지 않습니다. 이전에 저장된 문서 자체는 삭제하지 않습니다.
파일 하나의 실패가 다른 파일·공고의 처리를 막지 않습니다.

## 로컬 검증

```powershell
$env:PYTHONPATH = "src"
python -B -m unittest discover -s tests/unit -p test_attachment_parser.py -v
python -B -m unittest discover -s tests/integration -p test_attachment_downloader.py -v
```

통합 테스트는 외부 지자체 사이트 대신 로컬 HTTP 서버를 사용합니다.
