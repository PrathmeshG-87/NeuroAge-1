from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.router import restore_assessments, router as v1_router
from app.api.v1.auth import router as auth_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestBodyLimitMiddleware
from app.db import models as _models
from app.db.base import Base
from app.db.session import engine
from app.services.ml_inference import get_inference_service

logger = logging.getLogger('neuroage.database')


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    try:
        if engine.dialect.name == 'sqlite' and not settings.is_production:
            Base.metadata.create_all(engine)
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        restore_assessments()
    except SQLAlchemyError as exc:
        logger.exception(
            'Database is unavailable or migrations have not been applied.'
        )
        raise RuntimeError(
            'Database startup failed. Check DATABASE_URL and run '
            '`python -m alembic -c alembic.ini upgrade head` from backend/.'
        ) from exc
    yield


def _database_status() -> str:
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        return 'ok'
    except SQLAlchemyError:
        logger.exception('Database health check failed.')
        return 'unavailable'


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description='AI-based brain age assessment API foundation.',
        lifespan=lifespan,
        docs_url='/docs',
        redoc_url='/redoc',
        openapi_url='/openapi.json',
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowlist,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=settings.max_request_body_bytes,
    )

    app.include_router(v1_router)
    app.include_router(auth_router)

    @app.get('/health', tags=['system'])
    async def health() -> dict[str, object]:
        ml_status = get_inference_service().get_status()
        database_status = _database_status()
        overall_status = (
            'ok'
            if ml_status['status'] == 'ready' and database_status == 'ok'
            else 'degraded'
        )
        return {
            'status': overall_status,
            'service': settings.app_name,
            'version': settings.app_version,
            'environment': settings.environment,
            'checks': {
                'database': database_status,
                'ml_service': ml_status['status'],
                'storage': 'ok',
            },
        }

    register_exception_handlers(app)
    return app


app = create_app()
