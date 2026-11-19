# 평가위원 공고 수집기 (JudgeFinder)

지자체 평가위원 모집 공고를 수집하고 SQLite에 저장한 뒤 공식 원문 URL을 조회하는 CLI 프로젝트입니다.

첨부파일 다운로드 사용법은 [다운로드 안내](docs/attachment-download.md)를 참고하세요.

## 시작하기

Python 3.10 이상을 사용하며, 프로젝트 루트에서 실행합니다.

```bash
python -m pip install -e .
```

기본 설정은 `config/config.toml`입니다. 처음 실행한다면 `config/config.example.toml`을
복사해 `timezone`, `db_path`, `enabled_sources`와 소스별 설정을 확인합니다.
기존 개인 설정은 덮어쓰지 않습니다. 기본 예제에는 fixture를 읽는 `sample_city`가 있으므로,
실제 수집 시에는 대상 소스를 선택하고 해당 소스의 `fixture_path`를 제거하거나 설정하지 않습니다.

```bash
judgefinder sources
judgefinder collect --date today
judgefinder list --date today
judgefinder collect --date 2026-10-26 --days 7
judgefinder list --date 2026-10-26 --days 7
```

`sources`는 활성 소스, `collect`는 수집·저장한 공고 URL, `list`는 DB에 저장된 URL을 출력합니다.
`--date`는 설정 타임존의 `today` 또는 `YYYY-MM-DD`이며, `--days`는 끝 날짜를 포함한 최근 N일입니다.
`--days` 기본값은 1입니다. 수집하지 않은 과거 데이터를 `list`가 새로 가져오지는 않습니다.

별도 수집 프로파일은 `config/batch-*.example.toml`에 있습니다.
전역 옵션 `--config-path`와 `--verbose`는 명령어 앞에 둡니다.

```bash
judgefinder --config-path config/batch-held-eighteen.example.toml sources
judgefinder --config-path config/batch-held-eighteen.example.toml --verbose collect --date today
```

## 하이브레인 원기관 URL 보완 수집

설정 파일의 최상위에 아래 옵션을 추가하면 기존 `collect`가 공식 게시판을 먼저 수집한 뒤
하이브레인의 **진행 중 목록**에서 같은 조회 기간에 등록·수정된 평가위원 공고의 관련 홈페이지 URL을 확인합니다.
기본값은 비활성화이며 개인 설정과 운영 DB 경로는 자동으로 바꾸지 않습니다.

```toml
[origin_recovery]
enabled = true
hibrain = true
max_pages = 3
timeout_seconds = 20.0
throttle_seconds = 0.3
```

하이브레인 본문을 공고 데이터로 저장하지 않습니다. 활성 기관의 `detail_url_template`과 일치하는
공식 URL만 후보로 연결하고, 해당 기관의 `detail_title_selector`, `detail_date_selector`,
`detail_body_selector`로 공식 제목·날짜·본문을 확인합니다. 상세 필드가 부족하거나 원문이 이미지뿐인 경우,
접속 실패, 모집 여부 미확인, 미등록 상세 경로는 `review_hold`로 보관합니다.
검색·페이지 조건이 달라도 기관·공식 게시판·게시물 ID가 같으면 기존 공고에 연결합니다.
기관이나 게시판이 다른 게시물을 제목 유사도로 합치지는 않습니다.

```bash
judgefinder --config-path config/config.toml collect --date today
judgefinder --config-path config/config.toml review-origins
judgefinder --config-path config/config.toml review-origins --status all
```

검토 명령은 네트워크 없이 후보 출처, 공식 URL·ID, 상태, 실패 이유, 검증한 본문과 날짜를 JSON 줄 단위로 출력합니다.
검증한 보완 공고는 기존 `notices`에 저장되어 `list`에서도 조회됩니다.
보완 수집이 실패해도 먼저 저장한 공식 게시판 결과는 유지됩니다.
보류 건은 발견일을 포함하는 기간으로 `collect`를 재실행하면 재확인하며, 확인된 공고는 다시 다운로드하지 않습니다.
공식 날짜가 조회 기간 밖이면 `outside_window`로 보관하므로, 하이브레인 등록일을 오늘의 공식 게시일로 바꾸지 않습니다.
이 기능이 진행 중 전체 공고나 원문이 사라진 과거 공고까지 복구하는 것은 아닙니다.

다른 조사에서 확보한 원기관 URL도 선택적으로 전달할 수 있습니다. `candidate_file`은 프로젝트 기준 JSON 경로이며,
`hibrain = false`와 함께 쓰면 하이브레인 조회 없이 전달된 후보와 보류 건만 확인합니다.

```toml
# [origin_recovery] 내부
candidate_file = "data/origin-candidates.json"
```

```json
[
  {
    "discovery_url": "https://www.hibrain.net/research/researches/34/recruitments/425/recruits/공고ID",
    "origin_url": "https://공식기관/설정된상세경로?게시물ID=123",
    "discovered_date": "2026-11-03"
  }
]
```

## 심의위원·심사위원 보완 검색

공식 게시판의 기본 수집이 끝난 뒤, 설정된 제목 검색과 날짜·상세 본문을 사용할 수 있는
활성 HTML 소스에서 `심의위원`과 `심사위원` 검색을 추가로 실행합니다. 사용 중인 설정 파일에
`[origin_recovery]`가 있다면 그 표의 값을 수정합니다.

```toml
[origin_recovery]
enabled = true
hibrain = false
committee_search = true
```

`hibrain = true`로 두면 하이브레인 보완도 함께 실행합니다. 추가 후보의 공식 제목과 본문에서
위원 모집과 제안서 평가·심사·심의 역할을 확인하고 공식 게시물 ID·URL로 중복을 제거합니다.
본문만으로 역할이 모호하면 공식 제목과 일치하는 사업명과 평가 역할을 같은 사이트의 HWPX 첨부에서
확인합니다. 이미지나 기타 첨부 형식에서만 역할을 설명하는 후보는 검토 보류로 남습니다.
결과 공개나 위원 명단 공고는 자동 저장에서 제외합니다.
`judgefinder --config-path <설정파일> review-origins`에서 보류 후보의 URL과 사유를 확인합니다.

이 옵션은 목록 등록일, 검색 파라미터, 공식 상세 URL 형식과 상세 제목·등록일·본문 선택자가
설정된 표준 HTML 수집기에 적용됩니다. RSS·JSON API와 별도의 폼 전송 처리가 필요한 수집기는
기존 경로로 수집합니다. 화성 사업계획서 선정심의위원처럼 키워드가 별도로 지정된 경로도
해당 설정으로 수집합니다.

## 수집 설정과 주의사항

- RSS와 HTML/JSON 수집을 지원합니다. 하남시와 관악구의 설정 예제는 HTML 방식입니다.
- 실제 수집 대상은 `enabled_sources`로 결정됩니다. 검증 완료가 운영 활성화를 뜻하지는 않습니다.
- 수집 범위는 게시판·검색 조건·최대 페이지 수에 한정됩니다. 본문·첨부파일에만 있는 모집 표현이나
  공식 화면에서 숨겨진 종료 공고는 누락될 수 있습니다. 기간을 늘려도 비공개 원문을 복구하지는 못합니다.
- 등록일은 명시적인 목록·상세 날짜 필드에서 읽으며, 게시기간 시작일이나 본문 서명일로 추정하지 않습니다.
- 다른 호스트의 공식 상세 원문은 HTML 프로파일의 `detail_origin`으로 명시합니다.
  경로·쿼리·인증정보·포트가 없는 HTTPS 출처와, 출처가 같고 검증된 ID를 삽입하는 절대 상세 URL 템플릿이 필요합니다.
  임의 외부 링크나 TLS 검증 우회를 허용하는 옵션이 아니며, 리다이렉트 정책도 변경하지 않습니다.
- `collect`는 소스별 오류를 경고 후 건너뛰므로 종료 코드 0만으로 전체 성공을 판단하지 않습니다.
  `--verbose` 로그, 저장된 데이터와 공식 원문을 함께 확인합니다. 0건 수집은 공고 부재의 증거가 아닙니다.
- 개인 설정, DB와 실수집 결과는 Git에서 제외합니다. `tests/fixtures`는 회귀 테스트 입력이므로 유지합니다.

## 수집 배치 선택

날짜별로 나뉘어 있던 보완 설정은 발견 경로별 배치로 통합했습니다.
새 경로도 발견 경로에 맞는 통합 배치에 추가합니다.
원기관 URL·파서·필터·요청 전략과 기존 활성 소스를 유지합니다.
카페·하이브레인 배치는 해당 서비스의 게시물을 저장하는 수집기가 아니라,
대조 과정에서 확보한 공식 게시판을 수집하는 설정입니다.

| 설정 파일 | 활성 소스 | 기본 저장 위치 |
|---|---:|---|
| `config/batch-cafe.example.toml` | 137 | `data/cafe.db` |
| `config/batch-hibrain.example.toml` | 66 | `data/hibrain.db` |
| `config/batch-committee.example.toml` | 1 | `data/committee.db` |
| `config/batch-cafe-additional-institutions.example.toml` | 12 | `data/cafe-additional-institutions.db` |
| `config/batch-public-institutions-seven.example.toml` | 7 | `data/public-institutions-seven.db` |

카페 통합 배치는 기존 날짜별 배치 18개를, 하이브레인 통합 배치는 기존
`hibrain`·`hibrain-recovery`·11월 16일 추가 배치를 대체합니다.
11월 18일 추가한 옥천 심의위원 경로는 `batch-committee.example.toml`로 옮겼습니다.
이 배치만 기본적으로 `committee_search = true`를 사용하며, 나머지 통합 배치는
기존과 같이 보완 검색을 기본 비활성화합니다.

```bash
judgefinder --config-path config/batch-cafe.example.toml sources
judgefinder --config-path config/batch-cafe.example.toml collect --date today --days 7
judgefinder --config-path config/batch-cafe.example.toml list --date today --days 7
judgefinder --config-path config/batch-hibrain.example.toml collect --date today --days 7
judgefinder --config-path config/batch-committee.example.toml collect --date today --days 7
judgefinder --config-path config/batch-committee.example.toml review-origins
```

`--days`는 원문 등록일 조회 범위이며 접수 마감 여부를 판정하지 않습니다.
카페·하이브레인 등록일과 공식 게시일이 달라 최근 며칠을 함께 조회하는 방식입니다.
`recruitment_only = false`인 소스는 평가결과·정정·마감 공고도 포함할 수 있어 게시 전 검토합니다.
공식 재게시 경로는 발행 기관의 이름·등록일·URL을 보존하므로 원기관과 별도 기록이 될 수 있습니다.

### 기존 설정과 DB 이어 쓰기

통합 배치의 기본 DB 경로는 위 표를 따릅니다. 이전 배치의 DB를 계속 사용할 때는
통합 설정의 `db_path`를 기존 DB 파일로 지정합니다. 이번 설정 통합은 기존 SQLite 파일이나
그 안의 기록을 이동·병합하지 않습니다. 자동 실행 스크립트에 이전 파일명이 있다면
위 통합 파일명으로 변경해야 합니다.
여러 날짜별 배치를 순회했다면 통합 파일은 한 번만 실행하도록 실행 목록도 중복 제거합니다.

개인 운영 설정에 여러 배치를 합칠 때는 필요한 `[sources.*]` 표와 `enabled_sources`를
함께 추가하고 하나의 `db_path`를 지정합니다. 남양주·부천처럼 같은 소스 ID가 서로 다른
지역 배치에 존재하는 경우에는 URL·상세 프로파일을 확인해 사용할 설정을 선택합니다.
검증 배치의 활성화가 개인 운영 설정에 자동 반영되지는 않습니다.

### 지역별 배치

지역별 배치는 서로 다른 실행 범위를 제공하므로 유지합니다. 기존 활성 목록과 DB 경로를 사용합니다.

| 설정 파일 | 활성 소스 |
|---|---:|
| `config/batch-busan-daegu-ten.example.toml` | 10 |
| `config/batch-busan-ten.example.toml` | 10 |
| `config/batch-chungbuk-chungnam-jeonbuk-thirty.example.toml` | 28 |
| `config/batch-daegu-incheon-ten.example.toml` | 10 |
| `config/batch-daejeon-ulsan-sejong-gyeonggi-ten.example.toml` | 9 |
| `config/batch-gyeonggi-cities-next-ten.example.toml` | 10 |
| `config/batch-gyeonggi-cities-ten.example.toml` | 10 |
| `config/batch-gyeonggi-gangwon-chungbuk-thirty.example.toml` | 28 |
| `config/batch-gyeongnam-jeju-final-twenty.example.toml` | 22 |
| `config/batch-held-eighteen.example.toml` | 4 |
| `config/batch-incheon-jeonnam-ten.example.toml` | 12 |
| `config/batch-jeonbuk-gyeongbuk-gyeongnam-thirty.example.toml` | 25 |
| `config/batch-jeonnam-counties-ten.example.toml` | 12 |
| `config/batch-jeonnam-daejeon-ten.example.toml` | 10 |
| `config/batch-jeonnam-gwangju-ten.example.toml` | 13 |
| `config/batch-seoul-busan-ten.example.toml` | 13 |
| `config/batch-seoul-five.example.toml` | 5 |
| `config/batch-seoul-ten.example.toml` | 17 |

### 기관별 요청 방식

- 경남교육청 등 일부 게시판은 같은 세션의 직전 페이지에서 공개 양식 토큰을 읽어
  다음 페이지를 조회합니다. 토큰이 없거나 모호하면 실패 처리하며 저장 URL에 토큰을 넣지 않습니다.
- 원광대학교 공개 계약 게시판은 세션에 연결된 공개 POST 폼을 사용합니다.
  브라우저에서는 공식 계약 목록에서 공고를 선택해야 하며 저장 URL에 폼 토큰을 포함하지 않습니다.
- 서대문구도시관리공단은 `request_strategy.transport = "windows_curl"`을 사용합니다.
  Windows 기본 Schannel curl 7.83 이상이 필요하며 인증서 검증을 유지합니다.
  다른 기관은 기존 Requests 방식을 사용합니다. 다른 운영체제에서는 해당 소스를 제외하거나
  검증된 별도 접속 방식을 설정해야 합니다.
- 다른 호스트의 공개 상세 경로는 `detail_origin`으로 명시합니다. 게시물 ID만 보고
  등록되지 않은 호스트나 게시판으로 경로를 추측하지 않습니다.
- `keywords`는 해당 소스의 검색과 후보 필터에만 적용됩니다. 기본값은 `평가위원`이며,
  화성 선정심의위원·익산 제안서 선정위원처럼 별도 키워드를 사용하는 경로가 있습니다.

## 최신 공고 중심 검색 기간

고정된 과거 검색 날짜 대신 각 사이트의 기본 검색 기간과 `collect` 조회 기간을 사용합니다.
행정구역 신설 전 자료를 섞지 않기 위한 `available_from`은 유지합니다.
테스트 fixture의 과거 날짜는 파서 검증용이며 운영 검색 종료일이 아닙니다.

등록일 메타데이터가 필요한 게시판은 `listing_date_attribute` 또는 `detail_date_attribute`로
명시적인 날짜 속성을 읽습니다. 속성이 없거나 유효하지 않으면 접수기간·본문 서명일·사업연도로
대체하지 않습니다. 제목의 검색 강조나 UI 표시는 제거할 수 있지만 원문 제목과 출처는 보존합니다.

## 검증과 테스트

```bash
python -m pip install -e ".[dev]"
pytest -q
```

저장된 fixture로 파싱, 페이지 이동, 원문 검증, DB 중복 제거와 CLI 조회를 검사합니다.
다운로드 통합 테스트는 로컬 HTTP 서버를 사용하므로 로컬 서버 연결을 허용하는 환경이 필요합니다.
현재 공식 사이트의 정상 수집 여부는 별도 실수집·원문 대조로 확인해야 합니다.
