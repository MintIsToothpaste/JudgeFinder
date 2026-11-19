from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date

from judgefinder.domain.entities import Notice
from judgefinder.domain.notice_classification import (
    NoticeCategory,
    classify_committee_notice,
    classify_notice,
)
from judgefinder.domain.origins import (
    OriginCandidate,
    OriginDetails,
    OriginDiscovery,
    OriginReader,
    OriginStore,
)

LOGGER = logging.getLogger(__name__)


class CollectOriginNoticesUseCase:
    def __init__(self, store: OriginStore, reader: OriginReader,
                 discoveries: Sequence[OriginDiscovery], *, committee_search: bool = False) -> None:
        self.store, self.reader = store, reader
        self.discoveries = list(discoveries)
        self.committee_search = committee_search

    def execute(self, start: date, end: date) -> list[Notice]:
        if start > end:
            raise ValueError("Origin collection start must not follow its end")
        for discovery in self.discoveries:
            try:
                for candidate in discovery.discover(start, end):
                    record_id = self.store.enqueue(candidate)
                    if not candidate.origin_url:
                        self.store.attempt(record_id)
                        self.store.finish(
                            record_id, "review_hold", candidate.discovery_error or
                            "Original URL missing",
                        )
            except Exception as exc:
                record_id = self.store.enqueue(OriginCandidate(discovery.label, "", end))
                self.store.attempt(record_id)
                self.store.finish(record_id, "review_hold", f"Discovery failed: {exc}")
                LOGGER.warning("Origin discovery held: %s", exc)

        notices: list[Notice] = []
        existing: dict[str, list[Notice]] = {}
        for record in self.store.pending(start, end):
            committee = record.candidate.from_committee_search
            if committee and not self.committee_search:
                continue
            self.store.attempt(record.id)
            route = None
            details = None
            try:
                route = self.reader.resolve(record.candidate.origin_url)
                if route.municipality not in existing:
                    existing[route.municipality] = self.store.existing_notices(route.municipality)
                matches = [n for n in existing[route.municipality] if self.reader.identity(
                    n.municipality, n.url,
                ) == route.identity_key]
                if matches:
                    self.store.save_verified(
                        record.id, route, OriginDetails(matches[0], ""),
                        [n.url for n in matches],
                    )
                    continue
                details = (self.reader.read(route, committee_search=True) if committee
                           else self.reader.read(route))
                if not start <= details.notice.published_date <= end:
                    self.store.finish(
                        record.id, "outside_window", "Official publication date outside window",
                        route=route, details=details,
                    )
                    continue
                title = details.notice.title
                body = details.body_text
                reason = ""
                if committee:
                    category = classify_committee_notice(title, body, details.attachment_text)
                    if category is NoticeCategory.RESULT:
                        reason = "Official notice is a result announcement"
                    elif category is not NoticeCategory.RECRUITMENT:
                        reason = ("Official evaluator recruitment unconfirmed" if body
                                  else "Official notice body is empty")
                elif classify_notice(title, body) is not NoticeCategory.RECRUITMENT:
                    reason = "Official evaluator recruitment unconfirmed"
                if reason:
                    self.store.finish(
                        record.id, "review_hold", reason,
                        route=route, details=details,
                    )
                    continue
                if self.store.save_verified(record.id, route, details, []):
                    notices.append(details.notice)
                    existing[route.municipality].append(details.notice)
            except Exception as exc:
                self.store.finish(
                    record.id, "review_hold", str(exc), route=route, details=details,
                )
                LOGGER.warning("Official origin held: %s: %s", record.candidate.origin_url, exc)
        return notices
