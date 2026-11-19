from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from judgefinder.domain.entities import Notice, SourceType
from judgefinder.domain.origins import OriginCandidate, OriginDetails, OriginRecord, OriginRoute
from judgefinder.infrastructure.db.models import (
    NoticeModel,
    NoticeOriginIdentityModel,
    OriginCandidateModel,
)


class SqlAlchemyOriginStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def enqueue(self, candidate: OriginCandidate) -> int:
        now = datetime.now(timezone.utc)
        statement = sqlite_insert(OriginCandidateModel).values(
            discovery_url=candidate.discovery_url, origin_url=candidate.origin_url,
            discovered_date=candidate.discovered_date, first_seen_at=now, last_seen_at=now,
            status="pending", reason="", source_slug="", canonical_url="", official_id="",
            body_text="", attempts=0,
        )
        statement = statement.on_conflict_do_update(
            index_elements=["discovery_url", "origin_url"],
            set_={"last_seen_at": now, "discovered_date": func.max(
                OriginCandidateModel.discovered_date, statement.excluded.discovered_date,
            )},
        )
        with self.session_factory() as session:
            session.execute(statement)
            record_id = session.scalar(select(OriginCandidateModel.id).where(
                OriginCandidateModel.discovery_url == candidate.discovery_url,
                OriginCandidateModel.origin_url == candidate.origin_url,
            ))
            session.commit()
            assert record_id is not None
            return record_id

    def pending(self, start: date, end: date) -> list[OriginRecord]:
        with self.session_factory() as session:
            return [self._record(row) for row in session.scalars(select(OriginCandidateModel).where(
                OriginCandidateModel.discovered_date.between(start, end),
                or_(
                    OriginCandidateModel.status.in_(["pending", "review_hold"]),
                    and_(OriginCandidateModel.status == "outside_window",
                         OriginCandidateModel.published_date.between(start, end)),
                ),
                OriginCandidateModel.origin_url != "",
            ).order_by(OriginCandidateModel.id)).all()]

    def list_records(self, status: str | None = "review_hold") -> list[OriginRecord]:
        statement = select(OriginCandidateModel).order_by(OriginCandidateModel.id)
        if status is not None:
            statement = statement.where(OriginCandidateModel.status == status)
        with self.session_factory() as session:
            return [self._record(row) for row in session.scalars(statement).all()]

    def attempt(self, record_id: int) -> None:
        with self.session_factory() as session:
            record = session.get(OriginCandidateModel, record_id)
            assert record is not None
            record.attempts += 1
            record.last_checked_at = datetime.now(timezone.utc)
            session.commit()

    @staticmethod
    def _finish(record: OriginCandidateModel, status: str, reason: str,
                route: OriginRoute | None, details: OriginDetails | None) -> None:
        record.status, record.reason = status, reason[:2048]
        if route is not None:
            record.source_slug = route.source_slug
            record.canonical_url = route.canonical_url
            record.official_id = route.official_id
        if details is not None:
            record.official_title = details.notice.title
            record.published_date = details.notice.published_date
            record.body_text = details.body_text

    def finish(self, record_id: int, status: str, reason: str, *,
               route: OriginRoute | None = None, details: OriginDetails | None = None) -> None:
        with self.session_factory() as session:
            record = session.get(OriginCandidateModel, record_id)
            assert record is not None
            self._finish(record, status, reason, route, details)
            session.commit()

    def existing_notices(self, municipality: str) -> list[Notice]:
        with self.session_factory() as session:
            return [Notice(
                id=r.id, municipality=r.municipality, title=r.title, url=r.url,
                published_date=r.published_date, fetched_at=r.fetched_at,
                source_type=SourceType(r.source_type),
            ) for r in session.scalars(select(NoticeModel).where(
                NoticeModel.municipality == municipality,
            ).order_by(NoticeModel.id)).all()]

    def save_verified(self, record_id: int, route: OriginRoute, details: OriginDetails,
                      equivalent_urls: list[str]) -> bool:
        with self.session_factory() as session:
            # Serialize identity claims with other collectors using this SQLite database.
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            identity = session.get(NoticeOriginIdentityModel, route.identity_key)
            notice = session.get(NoticeModel, identity.notice_id) if identity else session.scalar(
                select(NoticeModel).where(
                    NoticeModel.municipality == route.municipality,
                    NoticeModel.url.in_([route.canonical_url, *equivalent_urls]),
                ).order_by(NoticeModel.id),
            )
            if identity is not None and notice is None:
                raise ValueError("Official identity references a missing saved notice")
            if details.notice.municipality != route.municipality:
                raise ValueError("Official detail municipality differs from its route")
            if not equivalent_urls and details.notice.url != route.canonical_url:
                raise ValueError("Official detail URL differs from its route")
            created = notice is None
            if notice is None:
                n = details.notice
                notice = NoticeModel(
                    municipality=n.municipality, title=n.title, url=n.url,
                    published_date=n.published_date, fetched_at=n.fetched_at,
                    source_type=n.source_type.value,
                )
                session.add(notice)
                session.flush()
            if identity is None:
                session.add(NoticeOriginIdentityModel(
                    identity_key=route.identity_key, notice_id=notice.id,
                ))
            record = session.get(OriginCandidateModel, record_id)
            assert record is not None
            self._finish(record, "collected" if created else "duplicate", "", route, details)
            record.notice_id = notice.id
            session.commit()
            return created

    @staticmethod
    def _record(row: OriginCandidateModel) -> OriginRecord:
        return OriginRecord(
            id=row.id, candidate=OriginCandidate(
                row.discovery_url, row.origin_url, row.discovered_date,
            ), status=row.status, reason=row.reason, source_slug=row.source_slug,
            canonical_url=row.canonical_url, official_id=row.official_id,
            body_text=row.body_text, attempts=row.attempts,
            official_title=row.official_title, published_date=row.published_date,
            notice_id=row.notice_id,
        )
