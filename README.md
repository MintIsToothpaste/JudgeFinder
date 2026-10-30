# 평가위원 공고 수집기 (JudgeFinder)

지자체 평가위원 모집 공고를 수집하고 SQLite에 저장한 뒤 공식 원문 URL을 조회하는 CLI 프로젝트입니다.

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

## 카페 대조에서 누락된 게시판 보완

- `config/batch-seoul-ten.example.toml`은 기존 공지사항·통합검색과 함께
  `yangcheon_gosi`, `gangbuk_gosi`, `seodaemun_gosi`, `mapo_gosi` 전자민원 고시공고 소스를 활성화합니다.
- `config/batch-seoul-busan-ten.example.toml`은 기존 게시판과 함께
  `busan_gosi`, `seocho_katia`, `gangnam_union6`를 활성화합니다.
  부산 고시공고는 통합 공지사항과 별도 게시판이며, 강남 `union6`는 재건축 관련 게시판입니다.
- `seodaemun_gosi`, `mapo_gosi`, `gangnam_union6`는 `recruitment_only = false`로 넓게 수집합니다.
  제목·등록일은 상세 원문의 명시된 필드로 확인하며, 접수기간으로 등록일을 대신하지 않습니다.
  서대문 북가좌·마포 소식지/방송·강남 수서한아름 표본의 기관 등록일은 모두 2026-10-23입니다.
  이 표본은 `collect --date 2026-10-24 --days 7`로 재현할 수 있습니다.
- `seocho_katia`는 교통영향평가협회의 서초 관련 공개 모집 글을 읽는 보조 소스입니다.
  지역 표기에 협회명을 포함하며, 날짜는 구청 공고일이 아닌 협회 게시일입니다.
- 경북 및 부산 통합 공지사항 URL의 고정 검색 종료일을 제거했습니다.
  포털의 기본 검색 기간은 적용되므로 장기 과거 수집 범위는 별도로 확인해야 합니다.
- 개인 운영 설정을 사용한다면 필요한 새 `[sources.*]` 설정과 소스 이름을
  해당 설정의 `enabled_sources`에도 추가해야 합니다.

카페 게시일과 기관 공고일이 다를 수 있어 최근 날짜를 함께 수집해 대조합니다.
아래 명령은 각 설정의 DB에 수집 결과를 저장합니다.

```bash
judgefinder --config-path config/batch-seoul-ten.example.toml collect --date today --days 7
judgefinder --config-path config/batch-seoul-busan-ten.example.toml collect --date today --days 7
judgefinder --config-path config/batch-jeonbuk-gyeongbuk-gyeongnam-thirty.example.toml collect --date today --days 7
```

## 추가 기관 수집 배치

`config/batch-cafe-additional-institutions.example.toml`은 화성시인재육성재단,
창원레포츠파크, 부산경제진흥원, 부산테크노파크, 부산과학기술고등교육진흥원,
대전 중구, 의성군의 공개 게시판을 수집합니다. 부산경제진흥원은 지원사업 5개 분야와
공고/공지사항을 각각 읽으므로 7개 기관에 12개 소스를 사용합니다.

```bash
judgefinder --config-path config/batch-cafe-additional-institutions.example.toml sources
judgefinder --config-path config/batch-cafe-additional-institutions.example.toml collect --date today --days 7
judgefinder --config-path config/batch-cafe-additional-institutions.example.toml list --date today --days 7
```

기본 저장소는 `data/cafe-additional-institutions.db`입니다. 기존 지자체 배치는 그대로 사용하며,
하나의 운영 설정으로 합칠 때는 새 소스 설정과 `enabled_sources`를 모두 추가하고
같은 `db_path`를 지정합니다. 이 배치 실행만으로 다른 배치나 개인 설정이 변경되지는 않습니다.

이 배치는 `recruitment_only = false`로 `평가위원` 키워드 공고를 넓게 수집합니다.
평가결과 공개·정정 전 원공고도 들어올 수 있으므로 게시 전에 사람이 검토합니다.
의성군·BISTEP의 잘린 목록 제목과 부산테크노파크의 중복 표시 제목은 상세 제목으로 보완합니다.
2026-10-27 대조 대상 9건 중 창원은 원문 등록일이 10월 23일, 나머지는 10월 26일이므로
`--date 2026-10-27 --days 7`로 재현할 수 있습니다. 당일 수집만으로는 이 9건이 나오지 않습니다.

## 직전 카페 수집분의 신규 기관 7곳

`config/batch-public-institutions-seven.example.toml`은 2026-10-24 카페 대조에서
빠졌던 다음 공개 수집 경로 7개를 활성화합니다.

- `national_heritage`: 국가유산청 공지사항. 국립문화유산연구원의 현미경시스템 공고를 포함합니다.
  연구원 전용 게시판이 아니므로 다른 국가유산청 평가위원 공고도 수집하며, 저장 표기에 출처를 남깁니다.
- `chungnam_state_university`: 충남도립대학교 공지사항.
- `pyeongchang_heritage`: 평창유산재단 공지사항.
- `gangwon_ccei`: 강원창조경제혁신센터의 공식 화면에서 사용하는 공개 JSON 목록.
- `busan_cultural_foundation`: 부산문화재단 공모·참여 게시판.
- `gyeongnam_future_education`: 경남교육청 미래교육원 공지사항.
  엠에스이씨엠이 발행하고 교육원이 게시한 공고를 포함하며, 수탁기관 공고가 포함됨을 저장 표기에 남깁니다.
- `gyeongnam_technopark_ktp`: 한국테크노파크진흥회에서 경남 지역만 조회하는 공식 재게시 목록.
  경남테크노파크 원문 URL을 저장하지만 등록일은 진흥회 게시일입니다.
  경남테크노파크 접수 시작일이나 공고문 서명일을 등록일로 추정하지 않습니다.

```bash
judgefinder --config-path config/batch-public-institutions-seven.example.toml collect --date 2026-10-24 --days 7
judgefinder --config-path config/batch-public-institutions-seven.example.toml list --date 2026-10-24 --days 7
```

기본 DB는 `data/public-institutions-seven.db`입니다. 일상 수집에는 `--date today --days 7`을 사용합니다.
기존 운영 설정에 합칠 때는 소스 설정과 `enabled_sources`를 함께 추가하고 같은 `db_path`를 지정합니다.
이 배치도 `recruitment_only = false`이며, 원문 제목의 `(마감)` 표시를 보존합니다.
수집 성공이 현재 접수 가능함을 뜻하지는 않습니다.

국가유산청과 충남도립대의 검색·페이지 조건은 `html_profile.detail_query_exclude`에
쉼표로 나열한 매개변수만 상세 URL에서 제거합니다. 게시글 식별자는 유지하며 기본값은 제거하지 않습니다.
충남도립대 등록일은 상세 화면의 명시적인 네 자리 연도(`2026. 10. 23.`)에서 읽습니다.
기존 지자체의 별도 누락 4건(서대문 1건, 마포 2건, 강남 1건)은 이 배치에 포함되지 않습니다.

## 검증과 테스트

지자체별 확인 완료·보류 현황은 [test-finish.md](docs/test-finish.md)에서 관리합니다.
저장된 fixture를 사용하는 회귀 테스트는 다음과 같이 실행합니다. 현재 공식 사이트의 정상 수집 여부는
별도 실수집·원문 대조로 확인해야 합니다.

```bash
python -m pip install -e ".[dev]"
pytest -q
```

## 10월 23일 카페 대조에서 추가한 공개 경로

`config/batch-cafe-20261023.example.toml`은 한국도시설계학회, 제물포구 공지사항,
과천도시공사, 충남도청, 충북도청 Citynet, 율곡국학진흥원, 전주문화재단,
경남·제주·서울교육청 및 경희대 경영대학의 제물포구 재게시 등 11개 공개 게시판을 읽습니다.
한국도시설계학회는 지자체 공고 재게시 출처이며 협회 게시일로 저장합니다.

```bash
judgefinder --config-path config/batch-cafe-20261023.example.toml collect --date 2026-10-23 --days 7
judgefinder --config-path config/batch-cafe-20261023.example.toml list --date 2026-10-23 --days 7
```

기본 DB는 `data/cafe-20261023.db`입니다. 기존 개인 설정에 합칠 때는 새 소스 설정과
`enabled_sources`를 함께 추가하고 같은 `db_path`를 지정합니다.

- 모든 새 소스는 `recruitment_only = false`입니다. 평가결과 등도 포함될 수 있어 게시 전 검토합니다.
- 원주 기존 소스도 넓게 수집하도록 바꿨습니다. `평가 심의위원`처럼 표기된 제목은
  `평가` 검색으로 찾고 설정한 공고 본문에서 `평가위원` 키워드를 확인합니다.
  일반 환경영향평가처럼 해당 키워드가 없는 공고는 저장하지 않습니다.
- 제물포 기존 고시공고의 시간만 표시된 목록 날짜는 상세 화면의 명시적 작성일로 보완합니다.
- 경남교육청은 같은 세션의 직전 페이지에서 공개 양식 토큰을 읽어 페이지를 이동합니다.
  토큰이 없거나 모호하면 오류로 처리하며, 저장되는 공고 URL에는 토큰을 넣지 않습니다.
- 2026-10-28 현재 전체 279개 경로의 실수집에서 10/23 카페 표본은 **24/28건** 일치했습니다.
  제물포 행정구역 조정·충북나드리는 현재 목록에서 발견되지 않았고,
  경기 학교 네트워크 감리·금산 마을기록관은 모집 원문 경로가 미확보입니다.
  따라서 새 경로 추가가 표본 28건의 완전 수집을 뜻하지는 않습니다.

### 제물포구 원문이 사라진 경우의 보조 경로

`jemulpo_khu`는 경희대학교 경영대학에서 **제목에 제물포구가 포함된 글**만 검색한 뒤
기존 평가위원 키워드 필터를 적용하는 공개 재게시 소스입니다. 위 배치에 함께 활성화했습니다.
구청 등록일 대신 대학의 명시적 등록일과 대학 원문 URL을 저장하며,
기관 표기에 `제물포구 (경희대학교 경영대학 재게시)`를 남깁니다.

2026-10-28 확인 시 행정구역 조정 공고는 구청 목록에서 빠졌고 구청 상세는 메인으로
리다이렉트됐습니다. 같은 모집 내용과 HWPX 첨부 링크 2개가 있는 대학 재게시는
10월 27일 등록되어 최근 7일 수집으로 확보됩니다.

```bash
judgefinder --config-path config/batch-cafe-20261023.example.toml collect --date 2026-10-28 --days 7
```

구청 원문 10/22와 대학 재게시 10/27은 출처·등록일이 다른 기록입니다.
따라서 재게시를 10/23 대조 결과에 소급 포함하지 않습니다. 모집기간은 10/27까지였으므로
이 표본을 복구했다는 것이 현재 접수 가능함을 뜻하지는 않습니다.
원문이 노출될 때 이미 저장한 DB 기록은 이후 목록에서 사라져도 삭제하지 않습니다.
원문과 재게시가 모두 수집되면 서로 다른 URL의 기록 2건이 남으며, 같은 사업 단위 통합은 아직 하지 않습니다.

## 10월 28일 카페 대조에서 복구한 경로

`config/batch-cafe-20261028.example.toml`에 다음 11개 공개 소스를 추가했습니다.
대한민국시도지사협의회, 경기교통공사, 경기도교육청 공고등록부, 인제군문화재단,
홍주문화관광재단, 진도 관련기관공지, 대구전통시장진흥재단, 서울 중구 고시공고,
속초 고시공고, 예천 전자민원, 세종 전자민원입니다.

```bash
judgefinder --config-path config/batch-cafe-20261028.example.toml collect --date today --days 7
judgefinder --config-path config/batch-cafe-20261028.example.toml list --date today --days 7
```

기본 DB는 `data/cafe-20261028.db`입니다. 기존 운영 설정에 합칠 때는 새 소스의 전체 설정과
`enabled_sources`를 함께 추가하고 같은 `db_path`를 사용합니다. 울산 수정은 기존
`batch-daejeon-ulsan-sejong-gyeonggi-ten.example.toml`의 `ulsan` 설정에 반영했습니다.
목록에 있는 공고 구분값(`gosiGbn=A/N`)을 유지하며 임의로 바꾸지 않습니다.
세종 포털은 날짜가 비어 있는 옛 공고 때문에 계속 보류하고, 게시일자가 있는
`sejong_eminwon`으로 수집합니다. 원문 접수기간을 누락된 등록일로 대체하지 않습니다.

새 배치는 `recruitment_only = false`라 평가결과 등도 포함될 수 있습니다.
일반 HTML 수집기의 키워드 비교는 `평가 위원`처럼 띄어 쓴 표기도 허용하고 원문 제목은 보존합니다.
2026-10-28 지역별 카페 표본 전체 36건을 재대조한 결과 **23/36 → 35/36건**으로 늘었습니다.
군포뉴스 평가위원 모집 원문 1건은 미확보이며 같은 사업의 업체 입찰공고로 대체하지 않았습니다.
이 표본 결과가 모든 지역의 완전 수집이나 첨부 다운로드 성공을 뜻하지는 않습니다.

## 10월 22일 카페 대조에서 추가한 경로

`config/batch-cafe-20261022.example.toml`은 제물포구 전자민원 고시공고, 천안도시공사,
김제교육지원청, 거제고현자율상권조합, 김해문화관광재단의 공개 게시판 5개를 읽습니다.
기존 지자체 배치와 함께 사용하며 운영 설정에 합칠 때는 소스의 전체 설정과
`enabled_sources`를 함께 추가해야 합니다. 기본 DB는 `data/cafe-20261022.db`입니다.

```bash
judgefinder --config-path config/batch-cafe-20261022.example.toml collect --date today --days 7
judgefinder --config-path config/batch-cafe-20261022.example.toml list --date today --days 7
```

새 소스는 `recruitment_only = false`로 수집합니다. 거제는 원문 제목에 평가위원 표현이 없어
제목+본문 검색과 지정한 공고 본문에서 키워드를 확인하며 공식 제목은 보존합니다.
김제의 명시적 등록일 `26.10.21`은 해당 프로필의 `two_digit_year_base = 2000`으로
`2026-10-21`로 읽습니다. 이 설정을 생략한 기존 경로는 두 자리 연도를 추정하지 않으며,
날짜가 잘못됐거나 누락되면 접수기간·공고문 서명일로 대체하지 않습니다.

대전 기존 소스는 `batch-jeonnam-daejeon-ten.example.toml`에 고정돼 있던 검색 기간을 제거했습니다.
2026-10-28 실조회에서 10/22 카페 표본은 **18/25 → 24/25건**으로 늘었습니다.
부산 소방차량 공고는 브라우저에서 공개되지만 Python에서 시간 초과·오류 화면·검색 미발견이
관찰돼 자동 수집 미해결로 남겼습니다. 삭제나 게시 종료로 확정한 것은 아닙니다.


## 10월 21일 카페 대조에서 추가한 경로

`config/batch-cafe-20261021.example.toml`은 서울시여성가족재단, 인천서해구문화원,
전남관광재단, 제주국제대학교 교원공지 4개 경로를 추가합니다. 기존 지자체 배치와 함께
사용하며 운영 설정에는 소스 설정 전체와 `enabled_sources`를 함께 반영해야 합니다.
기본 DB는 `data/cafe-20261021.db`이고 새 소스는 `recruitment_only = false`입니다.

```bash
judgefinder --config-path config/batch-cafe-20261021.example.toml collect --date today --days 7
judgefinder --config-path config/batch-cafe-20261021.example.toml list --date today --days 7
```

기존 제주 소스의 `conIfmStdt`·`conIfmEnddt` 고정 날짜는
`batch-gyeongnam-jeju-final-twenty.example.toml`에서 제거했습니다.
전남관광재단은 `?page=2`를 무시하므로 `page_path_template`으로 `/lists/2`를 요청하고
현재 페이지 표시를 검증합니다. 설정을 생략한 기존 경로의 URL 구성은 유지됩니다.
서해구문화원 제목의 `[2026-05-18]`은 등록일로 쓰지 않고 실제 등록일 `2026-10-20`을 보존합니다.

2026-10-28 실조회에서 10/21 카페 평가위원 표본은 **12/19 → 17/19건**으로 늘었습니다.
이 중 원기관 공고는 16건, 제주 소방행정은 대학 공식 재게시본 1건입니다.
대학 재게시본은 해당 대학의 등록일과 URL로 저장하므로 원기관 공고와 사업이 중복될 수 있습니다.
평택 보도육교 공고는 게재기간 종료·현재 목록 미노출, 인천 대토론회는 원문 공개·현재 목록
미노출로 분리했습니다. 두 건을 수집 성공으로 세거나 삭제로 확정하지 않았습니다.


## 최신 공고 중심 검색 기간

운영은 최신 평가위원 모집 공고의 빠른 발견을 우선합니다. 경남, 나주 2개 게시판,
장흥 2개 게시판, 강화의 과거 날짜로 고정된 검색 파라미터를 제거했습니다.
날짜를 생략한 게시판은 각 사이트의 기본 검색 기간을 사용합니다.
최근 며칠을 재조회하려면 `collect --date today --days 7`처럼 실행하며,
이 기간은 원문 등록일 기준입니다. 접수 마감 여부를 판정하는 옵션은 아닙니다.

행정구역 신설 전 자료를 섞지 않기 위한 `available_from`과 통합 광역자치단체의
명시적인 신설일 제한은 유지합니다. 예제 설정 전체에 고정 검색 날짜가 다시 들어오면
실패하는 회귀 테스트를 추가했습니다. 과거 자료 재현용 테스트 fixture의 날짜는 유지합니다.


## 10월 29일 카페 대조에서 추가한 경로

`config/batch-cafe-20261029.example.toml`에 공식 게시판 13개를 추가했습니다.
수원문화재단, 동일미래과학고, 진도군문화도시센터, 대구전통시장진흥재단 공고,
경상북도문화관광공사, 포항테크노파크, 서귀포시교육지원청, 울진 현재 공고,
영양축제관광재단, 대구테크노파크, 산청 전자공고, 대한교통학회 정보광장,
백석예술대학교 외부기관 공지가 대상입니다.
기존 지자체 배치와 함께 사용하며 운영 설정에는 소스 설정 전체와 `enabled_sources`를
함께 반영해야 합니다. 기본 DB는 `data/cafe-20261029.db`입니다.

```bash
judgefinder --config-path config/batch-cafe-20261029.example.toml collect --date today --days 7
judgefinder --config-path config/batch-cafe-20261029.example.toml list --date today --days 7
```

카페의 10/29 게시글 26건은 원기관 등록일이 10/23~10/28로 달랐습니다.
최근 7일 조회 후 DB 중복 방지로 **11/26 → 24/26 → 26/26건**을 확인했습니다.
서울 버스정보안내단말기는 대한교통학회, 강동 도로개선은 백석예술대학교의 공식 재게시본으로
확보했습니다. 해당 글의 HWPX 모집문에서 사업명·모집분야·접수기간을 대조했습니다.
두 경로는 재게시 기관 이름과 해당 기관의 등록일·URL로 저장합니다. 원기관 게시물과
대학 내 동일 공고의 다른 글 번호는 별개 URL이므로 사업 단위 중복 병합은 별도입니다.
새 게시판에는 `recruitment_only = false`를 적용하므로
취소·결과·접수마감 안내도 들어올 수 있고, 지원 가능 여부와 사람의 검수는 별도입니다.

진도는 `listing_date_attribute = "title"`로 상대 날짜 대신 HTML에 명시된 등록일을 읽습니다.
허용 속성은 `title`, `datetime`, `data-*`이며 목록 날짜 선택자가 필요합니다.
설정한 속성이 없거나 잘못되면 표시 날짜·접수기간으로 대체하지 않습니다.
울진의 기존 완료 공고 경로는 유지하고 현재 공고 경로를 별도로 추가했습니다.

대한교통학회는 `detail_date_attribute = "content"`로 상세의
`itemprop="datePublished"`에 명시된 등록일을 읽습니다. 화면의 `10.28`이나 제목의 사업연도로
등록 연도를 추정하지 않습니다. 이 선택 옵션은 상세 날짜 선택자가 필요하고,
`content`, `title`, `datetime`, `data-*` 속성을 허용합니다.


## 하이브레인에서 발견한 공식 수집 경로

`config/batch-hibrain.example.toml`은 원기관 공식 게시판 30개를 모은 보완 배치입니다.
기존 지자체 배치와 함께 운영하려면 `[sources.*]` 설정과 `enabled_sources`를 함께 합칩니다.
하이브레인은 원기관 경로 발견에만 사용하며 운영 수집 소스로 등록하지 않습니다.

```bash
judgefinder --config-path config/batch-hibrain.example.toml sources
judgefinder --config-path config/batch-hibrain.example.toml collect --date today --days 7
judgefinder --config-path config/batch-hibrain.example.toml list --date today --days 7
```

기본 DB는 `data/hibrain.db`입니다. 기존 DB를 이어 쓰려면 설정의 `db_path`를 해당 파일로 지정합니다.
`--days`는 원문 게시일 조회 범위이며 지원 가능 여부를 판정하지 않습니다.
노원구 고시공고는 기존 서울 배치에, 안산 게시일 수정은 기존 경기 배치에 반영되어 있습니다.
검수 결과와 성남 재단·안전보건공단 등의 남은 제약은
[하이브레인 경로 검증 기록](docs/hibrain-month-20261029.md)에 정리했습니다.

## 10월 30일 카페 대조 누락 보완

`config/batch-cafe-20261030.example.toml`은 인천창조경제혁신센터의 공개 JSON 공지사항과
안성산업진흥원의 공식 공지사항을 추가합니다. 두 소스는 `recruitment_only = false`로 넓게 수집합니다.
안성산업진흥원은 버튼의 영문·숫자 ID로 원문 URL을 만들고, 본문 서명일이 아닌 등록일을 사용합니다.
도봉구는 기존 서울 배치에 `dobong_gosi`를 추가해 공지사항과 별도 새올 고시공고를 함께 조회합니다.
도봉구 홈페이지의 고시공고 미러에도 일부 모집 공고가 빠져 있어 공식 새올 원문 목록을 사용합니다.

```bash
judgefinder --config-path config/batch-cafe-20261030.example.toml collect --date today --days 7
judgefinder --config-path config/batch-cafe-20261030.example.toml list --date today --days 7
judgefinder --config-path config/batch-seoul-ten.example.toml collect --date today --days 7
```

신규 기관 배치의 기본 DB는 `data/cafe-20261030.db`입니다. 개인 운영 설정으로 합칠 때는
소스 설정과 `enabled_sources`를 모두 추가해야 합니다. 카페 게시일과 원기관 게시일이 달라
최근 7일을 함께 수집하고 DB 중복 제거를 적용합니다.

기존 배치의 수원시는 변경된 현재 페이지 표시를 인식하며, 무안군은 차단 응답을 반환하는
이전 새올 호스트 대신 공식 홈페이지 고시공고를 조회합니다. 빈 검색 결과와 차단 문서는
구분하며 TLS 검증은 유지합니다.

## 과거 하이브레인 후보에서 확보한 공식 게시판

[하이브레인 보완 배치](config/batch-hibrain-recovery.example.toml)에 공식 게시판 14개를 추가했습니다.
기존 보완 경로 4개를 유지해 총 18개를 활성화하며 신규 14개는 recruitment_only = false로 넓게 수집합니다.
하이브레인은 경로 발견에만 사용하고 실제 수집은 원기관과 학회·재단의 공식 재게시 게시판에서 진행합니다.

~~~bash
judgefinder --config-path config/batch-hibrain-recovery.example.toml collect --date today --days 7
judgefinder --config-path config/batch-hibrain-recovery.example.toml list --date today --days 7
~~~

개인 운영 설정에는 소스 설정과 enabled_sources를 함께 반영해야 합니다.
부산TP는 만료일 대신 상세 작성일을 사용하고 영암군은 상세의 전체 제목을 읽습니다.
기존 5개 경로의 현재 목록 미노출과 수집 오류를 구분한 결과는
[경로 추가·실수집 검증 기록](docs/hibrain-routes65-20261030.md)에 정리했습니다.

대구전통시장진흥재단 사업공고(dtmsa_bid)와 대한인간공학회 채용·공고(esk_recruit)도 포함합니다.
재게시 공고는 해당 재단·학회의 기관명, 게시일, URL을 보존하므로 같은 사업이 다른 경로에도 존재할 수 있습니다.
