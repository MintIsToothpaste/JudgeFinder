package com.judgefinder.data.source.scraper

class ScraperRegistry(
    private val scrapers: Map<String, NoticeScraper>
) {
    fun scraperFor(sourceId: String): NoticeScraper? = scrapers[sourceId]
}
