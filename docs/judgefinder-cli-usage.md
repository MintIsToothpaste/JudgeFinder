# JudgeFinder CLI 사용법

`judgefinder`는 설정 파일(`config.toml`)에 등록된 소스에서 공고를 수집/조회하는 CLI입니다.

## 가상환경(venv) 진입

가상환경이 없다면 먼저 생성합니다.

```bash
python -m venv .venv
```

운영체제/셸에 맞게 가상환경을 활성화합니다.

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bat
:: Windows CMD
.\.venv\Scripts\activate.bat
```

```bash
# macOS / Linux
source .venv/bin/activate
```

가상환경 활성화 후 패키지를 설치합니다.

```bash
python -m pip install -e .
```

작업이 끝나면 가상환경을 종료합니다.

```bash
deactivate
```

## 기본 형식

```bash
judgefinder [전역 옵션] <command> [옵션]
```

## 전역 옵션

- `--config-path <파일경로>`: 설정 파일 경로 지정
  - 기본값: `config/config.toml`
- `--verbose`: 디버그 로그 출력

예시:

```bash
judgefinder --config-path config/config.toml --verbose sources
```

## 명령어

### 1) `sources`

현재 `enabled_sources`에 활성화된 소스 slug 목록을 출력합니다.

```bash
judgefinder sources
```

### 2) `collect`

지정한 날짜(또는 기간)의 공고를 수집해서 DB에 저장하고, 수집된 URL을 출력합니다.

옵션:

- `--date`: `today` 또는 `YYYY-MM-DD` (기본값: `today`)
- `--days`: `--date`를 끝 날짜로 하는 N일 범위 (기본값: `1`)

```bash
# 오늘 하루 수집
judgefinder collect

# 특정 날짜 하루 수집
judgefinder collect --date 2026-02-22

# 2026-02-22를 끝으로 최근 3일 수집 (2026-02-20 ~ 2026-02-22)
judgefinder collect --date 2026-02-22 --days 3
```

### 3) `list`

DB에 저장된 공고 URL을 날짜(또는 기간) 기준으로 조회합니다.

옵션:

- `--date`: `today` 또는 `YYYY-MM-DD` (기본값: `today`)
- `--days`: `--date`를 끝 날짜로 하는 N일 범위 (기본값: `1`)

```bash
# 오늘 저장된 URL 조회
judgefinder list

# 특정 날짜 조회
judgefinder list --date 2026-02-22

# 최근 7일 조회
judgefinder list --date 2026-02-22 --days 7
```

## 날짜 규칙

- `--date today`: 설정된 timezone 기준 오늘 날짜
- `--date YYYY-MM-DD`: ISO 형식 날짜
- 잘못된 날짜 형식이면 에러:
  - `Date must be 'today' or YYYY-MM-DD.`

## 출력 형식

- `collect`: 수집된 공고 URL을 한 줄씩 출력
- `list`: 저장된 공고 URL을 한 줄씩 출력
- `sources`: 활성화된 source slug를 한 줄씩 출력
