package com.judgefinder.domain.title

import com.judgefinder.domain.model.FieldCategory
import com.judgefinder.domain.model.Notice
import com.judgefinder.domain.model.Region
import kotlinx.datetime.LocalDate

class NoticeTitleGenerator {
    fun generate(notice: NoticeInput): String {
        val parts = buildList {
            notice.startDate?.let { add("[${it.format()}]") }
            notice.region?.let { add("[${it.displayName}]") }
            val fields = notice.recruitmentFields.takeIf { it.isNotEmpty() }?.joinToString("/") { it.displayName }
            if (!fields.isNullOrBlank()) add("[${fields}]")
        }

        val cleanedTitle = notice.rawTitle
            .replace("\\s+".toRegex(), " ")
            .replace("\n", " ")
            .trim()

        return if (parts.isEmpty()) {
            cleanedTitle
        } else {
            parts.joinToString(" ") + " " + cleanedTitle
        }
    }

    private fun LocalDate.format(): String = "%02d.%02d".format(monthNumber, dayOfMonth)

    data class NoticeInput(
        val rawTitle: String,
        val startDate: LocalDate?,
        val region: Region?,
        val recruitmentFields: List<FieldCategory>
    )

    companion object {
        fun fromNotice(notice: Notice): NoticeInput = NoticeInput(
            rawTitle = notice.rawTitle,
            startDate = notice.startDate,
            region = notice.region,
            recruitmentFields = notice.recruitmentFields
        )
    }
}
