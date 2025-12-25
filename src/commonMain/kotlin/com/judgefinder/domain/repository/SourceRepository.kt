package com.judgefinder.domain.repository

import com.judgefinder.domain.source.NoticeSource

interface SourceRepository {
    suspend fun enabledSources(): List<NoticeSource>
}
