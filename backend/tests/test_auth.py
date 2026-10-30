from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_registration_login_and_current_user_flow() -> None:
    registered = client.post(
        '/api/v1/auth/register',
        json={
            'full_name': '  Researcher One  ',
            'email': 'RESEARCHER@example.org',
            'password': 'correct horse battery staple',
        },
    )

    assert registered.status_code == 201, registered.text
    registration_payload = registered.json()
    assert registration_payload['user']['email'] == 'researcher@example.org'
    assert registration_payload['user']['display_name'] == 'Researcher One'
    assert 'password' not in registration_payload['user']

    logged_in = client.post(
        '/api/v1/auth/login',
        json={
            'email': 'researcher@example.org',
            'password': 'correct horse battery staple',
        },
    )
    assert logged_in.status_code == 200, logged_in.text
    token_payload = logged_in.json()
    assert token_payload['token_type'] == 'bearer'
    assert token_payload['expires_in'] == 30 * 60
    assert token_payload['access_token']

    current_user = client.get(
        '/api/v1/auth/me',
        headers={'Authorization': f"Bearer {token_payload['access_token']}"},
    )
    assert current_user.status_code == 200, current_user.text
    assert current_user.json()['user'] == registration_payload['user']


def test_registration_rejects_duplicate_and_invalid_accounts() -> None:
    payload = {
        'full_name': 'Researcher Two',
        'email': 'duplicate@example.org',
        'password': 'correct horse battery staple',
    }
    assert client.post('/api/v1/auth/register', json=payload).status_code == 201

    duplicate = client.post(
        '/api/v1/auth/register',
        json={**payload, 'email': 'DUPLICATE@example.org'},
    )
    assert duplicate.status_code == 409

    invalid = client.post(
        '/api/v1/auth/register',
        json={**payload, 'email': 'invalid-email', 'password': 'short'},
    )
    assert invalid.status_code == 422
    error = invalid.json()['error']
    assert error['code'] == 'validation_error'
    assert error['details']
    assert all('ctx' not in item for item in error['details'])
    assert all('input' not in item for item in error['details'])


def test_login_rejects_unknown_account_and_wrong_password() -> None:
    for email, password in [
        ('missing@example.org', 'correct horse battery staple'),
        ('missing@example.org', 'wrong password'),
    ]:
        response = client.post(
            '/api/v1/auth/login',
            json={'email': email, 'password': password},
        )
        assert response.status_code == 401
        assert response.json()['error']['message'] == 'Email or password is incorrect.'

    registered = client.post(
        '/api/v1/auth/register',
        json={
            'full_name': 'Researcher Three',
            'email': 'login@example.org',
            'password': 'correct horse battery staple',
        },
    )
    assert registered.status_code == 201

    wrong_password = client.post(
        '/api/v1/auth/login',
        json={'email': 'login@example.org', 'password': 'wrong password'},
    )
    assert wrong_password.status_code == 401


def test_current_user_requires_a_valid_token() -> None:
    response = client.get('/api/v1/auth/me')
    assert response.status_code == 401
