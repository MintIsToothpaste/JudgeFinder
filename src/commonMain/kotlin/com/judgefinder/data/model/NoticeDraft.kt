package com.judgefinder.data.model

import com.judgefinder.domain.model.FieldCategory
import com.judgefinder.domain.model.Region
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate

data class NoticeDraft(
    val rawTitle: String,
    val startDate: LocalDate?,
    val region: Region?,
    val recruitmentFields: List<FieldCategory>,
    val url: String,
    val sourceId: String,
    val fetchedAt: Instant,
    val externalId: String? = null,
    val dueDate: LocalDate? = null,
    val organization: String? = null
)
