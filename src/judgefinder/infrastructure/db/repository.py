from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from judgefinder.domain.entities import Notice, SourceType
from judgefinder.domain.ports import NoticeRepository
from judgefinder.infrastructure.db.models import NoticeModel


class SqlAlchemyNoticeRepository(NoticeRepository):
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def save_many(self, notices: list[Notice]) -> None:
        if not notices:
            return

        values = [
            {
                "municipality": notice.municipality,
                "title": notice.title,
                "url": notice.url,
                "published_date": notice.published_date,
                "fetched_at": notice.fetched_at,
                "source_type": notice.source_type.value,
            }
            for notice in notices
        ]

        statement = sqlite_insert(NoticeModel).values(values)
        statement = statement.on_conflict_do_nothing(index_elements=["municipality", "url"])

        with self._session_factory() as session:
            session.execute(statement)
            session.commit()

    def list_by_date(self, target_date: date) -> list[Notice]:
        statement = (
            select(NoticeModel)
            .where(NoticeModel.published_date == target_date)
            .order_by(NoticeModel.id.asc())
        )

        with self._session_factory() as session:
            records = session.scalars(statement).all()

        return [self._to_entity(record) for record in records]

    def _to_entity(self, model: NoticeModel) -> Notice:
        return Notice(
            id=model.id,
            municipality=model.municipality,
            title=model.title,
            url=model.url,
            published_date=model.published_date,
            fetched_at=model.fetched_at,
            source_type=SourceType(model.source_type),
        )
