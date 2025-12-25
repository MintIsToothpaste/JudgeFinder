package com.judgefinder.data.source.api

import com.judgefinder.data.model.NoticeDraft

interface NoticeApiDataSource {
    suspend fun fetch(): List<NoticeDraft>
}

class StubNoticeApiDataSource : NoticeApiDataSource {
    override suspend fun fetch(): List<NoticeDraft> = emptyList()
}
