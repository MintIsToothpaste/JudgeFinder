from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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


class OriginCandidateModel(Base):
    __tablename__ = "origin_candidates"
    __table_args__ = (UniqueConstraint("discovery_url", "origin_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discovery_url: Mapped[str] = mapped_column(Text, nullable=False)
    origin_url: Mapped[str] = mapped_column(Text, nullable=False)
    discovered_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_slug: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    official_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    official_title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    published_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    body_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    notice_id: Mapped[int | None] = mapped_column(ForeignKey("notices.id"), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NoticeOriginIdentityModel(Base):
    __tablename__ = "notice_origin_identities"

    identity_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    notice_id: Mapped[int] = mapped_column(ForeignKey("notices.id"), nullable=False, index=True)
