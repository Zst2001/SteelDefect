from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine():
    settings = get_settings()
    return create_engine(
        settings.mysql_dsn,
        pool_pre_ping=True,
        pool_recycle=3600,
        future=True,
    )


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
