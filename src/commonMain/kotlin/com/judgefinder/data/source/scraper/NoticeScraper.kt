package com.judgefinder.data.source.scraper

import com.judgefinder.data.model.NoticeDraft

interface NoticeScraper {
    suspend fun fetchLatest(): List<NoticeDraft>
}
