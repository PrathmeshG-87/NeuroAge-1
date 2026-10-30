from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = [
        {
            key: value
            for key, value in error.items()
            if key not in {'ctx', 'input'}
        }
        for error in exc.errors()
    ]
    payload = {
        'error': {
            'code': 'validation_error',
            'message': 'Request validation failed.',
            'details': details,
            'request_id': str(uuid.uuid4()),
        }
    }
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=payload)


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    detail = getattr(exc, 'detail', 'Request failed.')
    payload = {
        'error': {
            'code': getattr(exc, 'code', 'http_error'),
            'message': detail if isinstance(detail, str) else 'Request failed.',
            'details': None,
            'request_id': str(uuid.uuid4()),
        }
    }
    status_code = getattr(exc, 'status_code', status.HTTP_500_INTERNAL_SERVER_ERROR)
    return JSONResponse(status_code=status_code, content=payload)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    payload = {
        'error': {
            'code': 'internal_server_error',
            'message': 'An unexpected server error occurred.',
            'details': None,
            'request_id': str(uuid.uuid4()),
        }
    }
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=payload)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
