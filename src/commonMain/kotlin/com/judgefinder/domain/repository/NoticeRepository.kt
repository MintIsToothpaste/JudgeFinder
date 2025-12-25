package com.judgefinder.domain.repository

import com.judgefinder.domain.model.FieldCategory
import com.judgefinder.domain.model.Notice
import com.judgefinder.domain.model.NoticeId
import com.judgefinder.domain.model.NoticeStatus
import com.judgefinder.domain.model.Region
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate

interface NoticeRepository {
    suspend fun upsertAll(notices: List<Notice>): UpsertResult
    suspend fun query(
        region: Region? = null,
        field: FieldCategory? = null,
        keyword: String? = null,
        startDateFrom: LocalDate? = null,
        startDateTo: LocalDate? = null,
        status: NoticeStatus? = null,
    ): List<Notice>

    suspend fun markRead(id: NoticeId): Notice?
    suspend fun archive(id: NoticeId): Notice?

    data class UpsertResult(
        val added: Int,
        val updated: Int,
        val skipped: Int,
        val errors: List<String> = emptyList()
    )
}
