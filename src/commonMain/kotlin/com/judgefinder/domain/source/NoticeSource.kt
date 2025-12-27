package com.judgefinder.domain.source

data class NoticeSource(
    val id: String,
    val type: SourceType,
    val enabled: Boolean = true,
    val regionCode: String? = null
)

enum class SourceType {
    SCRAPER, API
}
