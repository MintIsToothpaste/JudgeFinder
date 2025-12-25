package com.judgefinder.data.repository

import com.judgefinder.domain.repository.SourceRepository
import com.judgefinder.domain.source.NoticeSource

class InMemorySourceRepository(
    private val sources: List<NoticeSource>
) : SourceRepository {
    override suspend fun enabledSources(): List<NoticeSource> = sources.filter { it.enabled }
}
