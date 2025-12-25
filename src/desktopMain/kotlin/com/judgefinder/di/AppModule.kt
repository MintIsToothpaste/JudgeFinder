package com.judgefinder.di

import app.cash.sqldelight.db.SqlDriver
import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import com.judgefinder.data.repository.InMemorySourceRepository
import com.judgefinder.data.repository.SqlDelightNoticeRepository
import com.judgefinder.data.source.api.StubNoticeApiDataSource
import com.judgefinder.data.source.scraper.MapoNoticeScraper
import com.judgefinder.data.source.scraper.ScraperRegistry
import com.judgefinder.db.NoticeDatabase
import com.judgefinder.domain.repository.NoticeRepository
import com.judgefinder.domain.repository.SourceRepository
import com.judgefinder.domain.source.NoticeSource
import com.judgefinder.domain.source.SourceType
import com.judgefinder.domain.usecase.ArchiveNoticeUseCase
import com.judgefinder.domain.usecase.MarkNoticeReadUseCase
import com.judgefinder.domain.usecase.QueryNoticesUseCase
import com.judgefinder.domain.usecase.SyncNoticesUseCase

class AppModule {
    private val driver: SqlDriver by lazy {
        JdbcSqliteDriver(JdbcSqliteDriver.IN_MEMORY).also {
            NoticeDatabase.Schema.create(it)
        }
    }

    private val noticeRepository: NoticeRepository by lazy {
        SqlDelightNoticeRepository(driver)
    }

    private val sourceRepository: SourceRepository by lazy {
        InMemorySourceRepository(
            listOf(
                NoticeSource(id = "mapo_scraper", type = SourceType.SCRAPER, enabled = true)
            )
        )
    }

    private val scraperRegistry by lazy {
        ScraperRegistry(mapOf("mapo_scraper" to MapoNoticeScraper()))
    }

    private val apiDataSource = StubNoticeApiDataSource()

    val syncNoticesUseCase by lazy { SyncNoticesUseCase(noticeRepository, sourceRepository, scraperRegistry, apiDataSource) }
    val queryNoticesUseCase by lazy { QueryNoticesUseCase(noticeRepository) }
    val markNoticeReadUseCase by lazy { MarkNoticeReadUseCase(noticeRepository) }
    val archiveNoticeUseCase by lazy { ArchiveNoticeUseCase(noticeRepository) }
}
