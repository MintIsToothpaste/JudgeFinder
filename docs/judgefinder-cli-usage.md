# JudgeFinder CLI 사용 가이드

이 문서는 현재 코드(`src/judgefinder/interfaces/cli/main.py`) 기준의 실제 CLI 동작을 설명합니다.

## 1) 개요

`judgefinder`는 설정 파일(`config.toml`)에 등록된 지자체 소스에서 공고를 수집(`collect`)하고, 저장된 URL을 조회(`list`)하는 CLI입니다.

- 엔트리포인트: `judgefinder`
- 기본 설정 파일: `config/config.toml`
- 저장소: SQLite (`db_path`)

## 2) 실행 준비

```bash
python -m venv .venv
```

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
python -m pip install -e .
```

## 3) 설정 파일 형식

최소 필수 구조:

```toml
timezone = "Asia/Seoul"
db_path = "data/judgefinder.db"
enabled_sources = ["seongbuk"]

[sources.seongbuk]
municipality = "성북구"
source_type = "html"
list_url = "https://..."
```

필수 키:

- 최상위: `timezone`, `db_path`, `enabled_sources`, `[sources]`
- 소스별: `municipality`, `source_type`, `list_url`

선택 키(현재 로직 지원):

- `fixture_path`
- `engine_type`
- `access_profile`
- `fallback_strategy`
- `[sources.<slug>.request_strategy]`
- `session`, `referer`, `retries`, `timeout_seconds`, `throttle_seconds`

참고:

- `source_type` 허용값: `html`, `api`
- `--config-path`로 지정한 설정 파일은 실제로 존재해야 합니다.

## 4) 기본 형식

```bash
judgefinder [전역 옵션] <command> [옵션]
```

전역 옵션:

- `--config-path <파일경로>`: 설정 파일 경로 지정 (기본값: `config/config.toml`)
- `--verbose`: 디버그 로그 출력

## 5) 명령어

### 5-1) `sources`

활성화된 소스 slug(`enabled_sources`)를 한 줄씩 출력합니다.

```bash
judgefinder sources
```

### 5-2) `collect`

지정 날짜(또는 기간)의 공고를 수집해 DB에 저장하고 URL을 출력합니다.

옵션:

- `--date`: `today` 또는 `YYYY-MM-DD` (기본값: `today`)
- `--days`: 끝 날짜(`--date`) 기준 최근 N일 범위 (기본값: `1`, 최소 `1`)

```bash
# 오늘 수집
judgefinder collect

# 특정 날짜 수집
judgefinder collect --date 2026-02-22

# 2026-02-22 기준 최근 3일 수집
judgefinder collect --date 2026-02-22 --days 3
```

동작 포인트:

- 기간 계산: `end_date - (days - 1)`부터 `end_date`까지
- 동일 URL은 실행 단위에서 중복 출력하지 않음
- 개별 소스 실패 시 전체 중단하지 않고 해당 소스만 경고 후 스킵

### 5-3) `list`

DB에 저장된 URL을 날짜(또는 기간) 기준으로 조회합니다.

옵션:

- `--date`: `today` 또는 `YYYY-MM-DD` (기본값: `today`)
- `--days`: 끝 날짜(`--date`) 기준 최근 N일 범위 (기본값: `1`, 최소 `1`)

```bash
# 오늘 조회
judgefinder list

# 특정 날짜 조회
judgefinder list --date 2026-02-22

# 최근 7일 조회
judgefinder list --date 2026-02-22 --days 7
```

동작 포인트:

- 조회 결과 URL도 실행 단위에서 중복 출력하지 않음

## 6) 날짜 규칙

- `--date today`: 설정된 `timezone` 기준 오늘
- `--date YYYY-MM-DD`: ISO 날짜
- 잘못된 형식이면 에러: `Date must be 'today' or YYYY-MM-DD.`

## 7) 출력 형식 요약

- `collect`: 수집된 공고 URL
- `list`: 저장된 공고 URL
- `sources`: 활성화된 source slug

모든 출력은 기본적으로 한 줄당 1개 항목입니다.

## 8) 권장 실행 순서

이미 `config/config.toml`에 대상 지자체가 등록되어 있다면 아래 3개만 사용하면 됩니다.

```bash
judgefinder --config-path config/config.toml sources
judgefinder --config-path config/config.toml collect --date 2026-02-22
judgefinder --config-path config/config.toml list --date 2026-02-22
```