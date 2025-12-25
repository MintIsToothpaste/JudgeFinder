package com.judgefinder.domain.usecase

import com.judgefinder.data.model.NoticeDraft
import com.judgefinder.data.model.NoticeMapper
import com.judgefinder.data.source.api.NoticeApiDataSource
import com.judgefinder.data.source.scraper.ScraperRegistry
import com.judgefinder.domain.model.Notice
import com.judgefinder.domain.model.NoticeId
import com.judgefinder.domain.repository.NoticeRepository
import com.judgefinder.domain.repository.SourceRepository
import com.judgefinder.domain.source.SourceType
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.security.MessageDigest

class SyncNoticesUseCase(
    private val noticeRepository: NoticeRepository,
    private val sourceRepository: SourceRepository,
    private val scraperRegistry: ScraperRegistry,
    private val apiDataSource: NoticeApiDataSource
) {
    data class SyncResult(
        val added: Int,
        val updated: Int,
        val skipped: Int,
        val errors: List<String>
    )

    suspend operator fun invoke(): SyncResult = withContext(Dispatchers.Default) {
        val sources = sourceRepository.enabledSources()
        val notices = mutableListOf<Notice>()
        val errors = mutableListOf<String>()

        sources.forEach { source ->
            val drafts = try {
                when (source.type) {
                    SourceType.SCRAPER -> scraperRegistry.scraperFor(source.id)?.fetchLatest()
                        ?: emptyList()
                    SourceType.API -> apiDataSource.fetch()
                }
            } catch (e: Exception) {
                errors.add("${source.id}: ${e.message}")
                emptyList()
            }

            drafts.forEach { draft ->
                val notice = NoticeMapper.toNotice(draft) { draftId -> draftId.toNoticeId() }
                notices.add(notice)
            }
        }

        val upsert = noticeRepository.upsertAll(notices)
        SyncResult(
            added = upsert.added,
            updated = upsert.updated,
            skipped = upsert.skipped,
            errors = errors + upsert.errors
        )
    }

    private fun NoticeDraft.toNoticeId(): NoticeId {
        val seed = externalId ?: url
        val md = MessageDigest.getInstance("SHA-1")
        val bytes = md.digest("${sourceId}:$seed".toByteArray())
        val hex = bytes.joinToString(separator = "") { b -> "%02x".format(b) }
        return NoticeId(hex)
    }
}
