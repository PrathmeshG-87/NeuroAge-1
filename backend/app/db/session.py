from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def create_database_engine(database_url: str, *, debug: bool = False) -> Engine:
    engine_options = {
        'pool_pre_ping': True,
        'future': True,
        'echo': debug,
    }
    if database_url.startswith('sqlite'):
        engine_options['connect_args'] = {'check_same_thread': False}
        sqlite_path = make_url(database_url).database
        if sqlite_path and sqlite_path != ':memory:':
            Path(sqlite_path).expanduser().resolve().parent.mkdir(
                parents=True,
                exist_ok=True,
            )
    return create_engine(database_url, **engine_options)


engine = create_database_engine(settings.database_url, debug=settings.debug)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
