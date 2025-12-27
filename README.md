# JudgeFinder

Kotlin Multiplatform + Compose Desktop 기반의 "평가위원 공고 수집기" 스캐폴딩입니다. 지금은 Desktop(JVM) 실행을 우선 지원하며, 도메인/데이터 레이어는 Android/iOS 확장 가능 구조로 설계되어 있습니다.

## 프로젝트 구조
- **Domain (commonMain)**: Notice/Region/FieldCategory 모델, `NoticeTitleGenerator`, 리포지토리 인터페이스, 각종 유스케이스 포함.
- **Data (commonMain)**: `NoticeDraft`, Notice 매퍼, SQLDelight 기반 리포지토리 구현, 스크래퍼·API 인터페이스.
- **Desktop (desktopMain)**: Compose Desktop 엔트리포인트, Jsoup 예제 스크래퍼(Mapo), DI 와이어링.
- **SQLDelight 스키마**: `src/commonMain/sqldelight/com/judgefinder/db/NoticeDatabase.sq`에 upsert/query 헬퍼 포함.

## 실행 방법
Android Studio 또는 커맨드라인에서 실행합니다.
```
./gradlew run      # 단일 모듈일 때
# 또는
./gradlew :desktop:run
```
실행하면 Desktop 윈도우에서 Sync 버튼을 눌러 Mapo 스크래퍼로 샘플 데이터를 수집하고 인메모리 SQLDelight DB에 저장합니다.

## 제목 정규화 규칙
도메인 `NoticeTitleGenerator`가 `[MM.DD] [지역] [모집분야] rawTitle` 포맷을 강제합니다. 누락된 값은 생략하지만, 존재하는 값은 괄호 구조를 유지합니다. 다수의 모집 분야는 `/`로 조인하며, 공백·중복 괄호 등을 간단히 정리합니다.

## 새 스크래퍼 추가하기
1. `desktopMain`(또는 플랫폼별 소스셋)에서 Jsoup 등 JVM 도구를 활용해 `NoticeScraper`를 구현합니다.
2. 가능한 경우 region/fields/startDate가 채워진 `NoticeDraft` 목록을 반환하도록 만듭니다.
3. `ScraperRegistry`(예: `AppModule`)에 scraper를 등록하고, `SourceRepository` 구현에 `NoticeSource` 항목을 추가합니다.
4. `SyncNoticesUseCase`가 drafts를 `Notice`로 매핑하고 정규화된 제목을 생성하여 upsert합니다.

## 모집 분야 매핑 확장하기
- 스크래퍼/API가 `NoticeDraft`를 만들 때 사용하는 `FieldCategory` 목록에 새 항목을 추가합니다.
- `displayName`은 정규화된 제목에 노출되며, `code`는 필터링·중복 판정에 사용되는 안정적 식별자입니다.

## 추가 플랫폼/소스 확장
- API 연동은 `NoticeApiDataSource`(commonMain)를 구현하고, 플랫폼별 Ktor 클라이언트를 제공합니다.
- Android/iOS는 공통 도메인/데이터 코드를 재사용하며, SQLDelight 드라이버와 Compose UI 셸만 플랫폼별로 제공하면 됩니다.
