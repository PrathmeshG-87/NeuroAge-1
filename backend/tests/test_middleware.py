from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.middleware import RequestBodyLimitMiddleware


def test_request_body_limit_rejects_oversized_content_length() -> None:
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=4)

    @app.post('/upload')
    async def upload(request: Request) -> dict[str, int]:
        body = await request.body()
        return {'size': len(body)}

    response = TestClient(app).post('/upload', content=b'12345')

    assert response.status_code == 413
    payload = response.json()['error']
    assert payload['code'] == 'payload_too_large'
    assert 'size limit' in payload['message'].lower()
    assert payload['request_id']
