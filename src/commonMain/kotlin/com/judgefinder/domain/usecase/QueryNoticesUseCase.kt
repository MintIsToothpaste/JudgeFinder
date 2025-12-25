package com.judgefinder.domain.usecase

import com.judgefinder.domain.model.FieldCategory
import com.judgefinder.domain.model.Notice
import com.judgefinder.domain.model.NoticeStatus
import com.judgefinder.domain.model.Region
import com.judgefinder.domain.repository.NoticeRepository
import kotlinx.datetime.LocalDate

class QueryNoticesUseCase(
    private val noticeRepository: NoticeRepository
) {
    suspend operator fun invoke(
        region: Region? = null,
        field: FieldCategory? = null,
        keyword: String? = null,
        startDateFrom: LocalDate? = null,
        startDateTo: LocalDate? = null,
        status: NoticeStatus? = null
    ): List<Notice> = noticeRepository.query(region, field, keyword, startDateFrom, startDateTo, status)
}
