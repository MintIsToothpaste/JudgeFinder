package com.judgefinder.domain.usecase

import com.judgefinder.domain.model.Notice
import com.judgefinder.domain.model.NoticeId
import com.judgefinder.domain.repository.NoticeRepository

class MarkNoticeReadUseCase(private val noticeRepository: NoticeRepository) {
    suspend operator fun invoke(id: NoticeId): Notice? = noticeRepository.markRead(id)
}
