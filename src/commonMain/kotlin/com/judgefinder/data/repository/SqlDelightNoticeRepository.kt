package com.judgefinder.data.repository

import app.cash.sqldelight.db.SqlDriver
import com.judgefinder.db.NoticeDatabase
import com.judgefinder.domain.model.FieldCategory
import com.judgefinder.domain.model.Notice
import com.judgefinder.domain.model.NoticeId
import com.judgefinder.domain.model.NoticeStatus
import com.judgefinder.domain.model.Region
import com.judgefinder.domain.repository.NoticeRepository
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate

class SqlDelightNoticeRepository(driver: SqlDriver) : NoticeRepository {
    private val database = NoticeDatabase(driver)
    private val queries = database.noticeDatabaseQueries

    override suspend fun upsertAll(notices: List<Notice>): NoticeRepository.UpsertResult {
        var added = 0
        var updated = 0
        notices.forEach { notice ->
            val existing = queries.selectById(notice.id.value).executeAsOneOrNull()
            queries.upsertNotice(
                id = notice.id.value,
                rawTitle = notice.rawTitle,
                normalizedTitle = notice.normalizedTitle,
                startDate = notice.startDate?.toString(),
                regionCode = notice.region?.code,
                regionDisplay = notice.region?.displayName,
                recruitmentFields = notice.recruitmentFields.joinToString("|") { "${it.code}:${it.displayName}" },
                url = notice.url,
                sourceId = notice.sourceId,
                fetchedAt = notice.fetchedAt.toString(),
                dueDate = notice.dueDate?.toString(),
                organization = notice.organization,
                status = notice.status.name,
                read = if (notice.read) 1 else 0,
                archived = if (notice.archived) 1 else 0
            )
            if (existing == null) added++ else updated++
        }
        return NoticeRepository.UpsertResult(added = added, updated = updated, skipped = 0)
    }

    override suspend fun query(
        region: Region?,
        field: FieldCategory?,
        keyword: String?,
        startDateFrom: LocalDate?,
        startDateTo: LocalDate?,
        status: NoticeStatus?
    ): List<Notice> {
        val base = if (keyword.isNullOrBlank()) {
            queries.selectAll().executeAsList()
        } else {
            val key = "%${keyword}%"
            queries.selectByKeyword(key, key).executeAsList()
        }

        return base.map { entity -> entity.toNotice() }
            .filter { notice ->
                val matchesRegion = region?.code?.let { notice.region?.code == it } ?: true
                val matchesField = field?.code?.let { code -> notice.recruitmentFields.any { it.code == code } } ?: true
                val matchesStatus = status?.let { notice.status == it } ?: true
                val matchesStartFrom = startDateFrom?.let { s -> notice.startDate?.let { it >= s } ?: false } ?: true
                val matchesStartTo = startDateTo?.let { e -> notice.startDate?.let { it <= e } ?: false } ?: true
                matchesRegion && matchesField && matchesStatus && matchesStartFrom && matchesStartTo
            }
    }

    override suspend fun markRead(id: NoticeId): Notice? {
        queries.markRead(id.value)
        return queries.selectById(id.value).executeAsOneOrNull()?.toNotice()
    }

    override suspend fun archive(id: NoticeId): Notice? {
        queries.archive(id.value)
        return queries.selectById(id.value).executeAsOneOrNull()?.toNotice()
    }

    private fun com.judgefinder.db.Notices.toNotice(): Notice {
        val startDate = startDate?.let { LocalDate.parse(it) }
        val dueDate = dueDate?.let { LocalDate.parse(it) }
        val fetched = Instant.parse(fetchedAt)
        val region = regionCode?.let { Region(it, regionDisplay ?: it) }
        val fields = recruitmentFields.takeIf { it.isNotBlank() }?.split("|")?.map {
            val parts = it.split(":", limit = 2)
            FieldCategory(code = parts[0], displayName = parts.getOrElse(1) { parts[0] })
        } ?: emptyList()

        return Notice(
            id = NoticeId(id),
            rawTitle = rawTitle,
            normalizedTitle = normalizedTitle,
            startDate = startDate,
            region = region,
            recruitmentFields = fields,
            url = url,
            sourceId = sourceId,
            fetchedAt = fetched,
            dueDate = dueDate,
            organization = organization,
            status = NoticeStatus.valueOf(status),
            read = read == 1L,
            archived = archived == 1L
        )
    }
}
