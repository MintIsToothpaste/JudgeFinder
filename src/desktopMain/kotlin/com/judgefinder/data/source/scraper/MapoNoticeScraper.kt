package com.judgefinder.data.source.scraper

import com.judgefinder.data.model.NoticeDraft
import com.judgefinder.domain.model.FieldCategory
import com.judgefinder.domain.model.Region
import kotlinx.datetime.Clock
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime
import org.jsoup.Jsoup

class MapoNoticeScraper : NoticeScraper {
    override suspend fun fetchLatest(): List<NoticeDraft> {
        // Example uses a placeholder HTML snippet to keep the scaffold runnable without network access.
        val sampleHtml = """
            <html><body>
                <div class='notice'>
                    <a class='title' href='https://mapo.go.kr/notice/1'>아현동 정비계획 공고</a>
                    <span class='date'>2025-12-30</span>
                </div>
            </body></html>
        """
        val doc = Jsoup.parse(sampleHtml)
        val now = Clock.System.now().toLocalDateTime(TimeZone.currentSystemDefault()).date
        val region = Region(code = "mapo", displayName = "마포")
        val field = FieldCategory(code = "urban_planning", displayName = "도시계획")

        return doc.select("div.notice").map { element ->
            val title = element.selectFirst("a.title")?.text().orEmpty()
            val url = element.selectFirst("a.title")?.attr("href").orEmpty()
            val startDate = element.selectFirst("span.date")?.text()?.takeIf { it.isNotBlank() }
            NoticeDraft(
                rawTitle = title,
                startDate = startDate?.let { kotlinx.datetime.LocalDate.parse(it) },
                region = region,
                recruitmentFields = listOf(field),
                url = url,
                sourceId = "mapo_scraper",
                fetchedAt = Clock.System.now(),
                organization = "마포구청"
            )
        }.ifEmpty {
            listOf(
                NoticeDraft(
                    rawTitle = "샘플 공고",
                    startDate = now,
                    region = region,
                    recruitmentFields = listOf(field),
                    url = "https://mapo.go.kr/sample",
                    sourceId = "mapo_scraper",
                    fetchedAt = Clock.System.now()
                )
            )
        }
    }
}
