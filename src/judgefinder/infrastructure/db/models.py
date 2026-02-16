from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class NoticeModel(Base):
    __tablename__ = "notices"
    __table_args__ = (UniqueConstraint("municipality", "url", name="uq_notice_municipality_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    municipality: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    published_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
