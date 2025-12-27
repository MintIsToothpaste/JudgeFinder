package com.judgefinder.domain.model

import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate

data class Notice(
    val id: NoticeId,
    val rawTitle: String,
    val normalizedTitle: String,
    val startDate: LocalDate?,
    val region: Region?,
    val recruitmentFields: List<FieldCategory>,
    val url: String,
    val sourceId: String,
    val fetchedAt: Instant,
    val dueDate: LocalDate? = null,
    val organization: String? = null,
    val status: NoticeStatus = NoticeStatus.NEW,
    val read: Boolean = false,
    val archived: Boolean = false
)

enum class NoticeStatus {
    NEW, OPEN, CLOSED
}
