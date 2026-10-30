from __future__ import annotations

import uuid

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            'error': {
                'code': code,
                'message': message,
                'details': None,
                'request_id': str(uuid.uuid4()),
            }
        },
    )


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get('headers', []))
        content_length = headers.get(b'content-length')
        if content_length:
            try:
                body_size = int(content_length)
            except ValueError:
                await _error_response(
                    400,
                    'invalid_content_length',
                    'The request content length is invalid.',
                )(scope, receive, send)
                return
            if body_size > self.max_body_bytes:
                await _error_response(
                    413,
                    'payload_too_large',
                    'Request body is oversized and exceeds the configured size limit.',
                )(scope, receive, send)
                return

        received_bytes = 0
        response_started = False

        async def limited_receive():
            nonlocal received_bytes
            message = await receive()
            if message['type'] == 'http.request':
                received_bytes += len(message.get('body', b''))
                if received_bytes > self.max_body_bytes:
                    raise _RequestBodyTooLarge
            return message

        async def track_response_start(message):
            nonlocal response_started
            if message['type'] == 'http.response.start':
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, track_response_start)
        except _RequestBodyTooLarge:
            if response_started:
                raise
            await _error_response(
                413,
                'payload_too_large',
                'Request body is oversized and exceeds the configured size limit.',
            )(scope, receive, send)


class _RequestBodyTooLarge(Exception):
    pass
