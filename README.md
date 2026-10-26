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

## 검증과 테스트

지자체별 확인 완료·보류 현황은 [test-finish.md](docs/test-finish.md)에서 관리합니다.
저장된 fixture를 사용하는 회귀 테스트는 다음과 같이 실행합니다. 현재 공식 사이트의 정상 수집 여부는
별도 실수집·원문 대조로 확인해야 합니다.

```bash
python -m pip install -e ".[dev]"
pytest -q
```
