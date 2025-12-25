# JudgeFinder

Kotlin Multiplatform + Compose Desktop scaffold for collecting evaluator notices. The Desktop target is runnable today while the domain/data layers stay KMP-ready for Android/iOS later.

## Project layout
- **Domain (commonMain)**: Notice/Region/FieldCategory models, `NoticeTitleGenerator`, repositories, use cases.
- **Data (commonMain)**: `NoticeDraft`, mapper to `Notice`, repository implementations (SQLDelight), scraper/API interfaces.
- **Desktop (desktopMain)**: Compose Desktop entry point, Jsoup-based scraper example, dependency wiring.
- **SQLDelight schema**: `src/commonMain/sqldelight/com/judgefinder/db/NoticeDatabase.sq` defines the persistence layer with upsert/query helpers.

## Running
Use Android Studio or the command line:
```
./gradlew :desktop:run  // or simply gradlew run if single module
```
The desktop window provides a Sync button that fetches sample data via the Mapo scraper and persists to the in-memory SQLDelight database.

## Title generation rule
`NoticeTitleGenerator` (domain/commonMain) enforces the normalized title format: `[MM.DD] [지역] [모집분야] rawTitle`, omitting missing parts but keeping bracketed sections for available values. It trims whitespace and joins multiple fields with `/`.

## Adding a new scraper
1. Implement `NoticeScraper` in `desktopMain` (or platform-specific source set) using Jsoup or other JVM tools.
2. Produce `NoticeDraft` instances with region/fields/date filled when available.
3. Register the scraper in `ScraperRegistry` (see `AppModule`) and add a `NoticeSource` entry in the `SourceRepository` implementation.
4. The sync use case will map drafts to domain `Notice` items, generate normalized titles, and upsert them.

## Adding recruitment field mappings
- Extend the `FieldCategory` list used by scrapers/APIs when building `NoticeDraft`.
- Display names appear inside the normalized title. Codes are stable identifiers for filtering and deduplication.

## Extending to new sources or platforms
- API integrations should implement `NoticeApiDataSource` (commonMain) with Ktor clients per platform.
- Additional platforms (Android/iOS) can reuse the domain/data code; provide platform-specific drivers for SQLDelight and UI shells using Compose Multiplatform.
