from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from judgefinder.infrastructure.db.models import Base


def create_sqlite_engine(db_path: Path) -> Engine:
    return create_engine(f"sqlite:///{db_path}", future=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)
