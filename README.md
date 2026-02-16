# 평가위원 공고 수집기 (JudgeFinder)

지자체 평가위원 모집 공고를 수집/저장/조회하는 CLI 프로젝트입니다.

## Quick Start

```bash
python -m pip install -e .
judgefinder sources
judgefinder collect --date today
judgefinder list --date today
```

## Date Option

- `--date today` (기본값): `config/config.toml`의 타임존 기준 오늘 날짜
- `--date YYYY-MM-DD`: 특정 날짜

## Project Layout

- `src/judgefinder/domain`: 엔티티, 포트(프로토콜)
- `src/judgefinder/application`: 유스케이스
- `src/judgefinder/adapters`: 소스 레지스트리/소스 구현
- `src/judgefinder/infrastructure`: DB/HTTP 어댑터
- `src/judgefinder/interfaces`: CLI
- `tests`: 파서 단위 테스트, 수집 통합성 테스트
