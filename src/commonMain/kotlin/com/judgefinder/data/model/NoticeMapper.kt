package com.judgefinder.data.model

import com.judgefinder.domain.model.Notice
import com.judgefinder.domain.model.NoticeId
import com.judgefinder.domain.model.NoticeStatus
import com.judgefinder.domain.title.NoticeTitleGenerator

object NoticeMapper {
    fun toNotice(draft: NoticeDraft, idProvider: (NoticeDraft) -> NoticeId): Notice {
        val id = idProvider(draft)
        val titleGenerator = NoticeTitleGenerator()
        val normalized = titleGenerator.generate(
            NoticeTitleGenerator.NoticeInput(
                rawTitle = draft.rawTitle,
                startDate = draft.startDate,
                region = draft.region,
                recruitmentFields = draft.recruitmentFields
            )
        )

        return Notice(
            id = id,
            rawTitle = draft.rawTitle,
            normalizedTitle = normalized,
            startDate = draft.startDate,
            region = draft.region,
            recruitmentFields = draft.recruitmentFields,
            url = draft.url,
            sourceId = draft.sourceId,
            fetchedAt = draft.fetchedAt,
            dueDate = draft.dueDate,
            organization = draft.organization,
            status = NoticeStatus.NEW
        )
    }
}
