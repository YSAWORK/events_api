# tests/user_auth/test_jwt_service.py
# This file contains tests for the JWT service in the user authentication module.


###### IMPORT TOOLS ######
# global imports
import pytest
import logging
from datetime import datetime, timezone
from fastapi import HTTPException
from uuid import uuid4

# local imports
from src.security.jwt_service import (
    make_access_token,
    decode_token,
)
from src.security import jwt_service


# fixed current time for tests
FIXED_NOW = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


# lower jwt logger level to reduce noise in test output
@pytest.fixture(autouse=True)
def _quiet_jwt_logger():
    '''Fixture to set JWT logger level to ERROR to reduce test output noise.'''
    logging.getLogger("jwt").setLevel(logging.ERROR)


@pytest.fixture(autouse=True)
def _align_claims_and_alg(monkeypatch):
    '''Patch common claims and algorithm to fixed values for consistent testing.'''
    def _patched_common_claims(sub: str, token_type: str, jti: str | None) -> dict:
        now = datetime.now(timezone.utc)
        return {
            "sub": sub,
            "type": token_type,
            "jti": jti or str(uuid4()),
            "iat": int(now.timestamp()),
            "iss": "your-auth",
            "aud": "your-api",
        }

    monkeypatch.setattr(
        jwt_service, "_jwt_common_claims", _patched_common_claims, raising=True
    )
    settings = jwt_service.get_settings()
    try:
        monkeypatch.setattr(settings, "JWT_ALG", "HS256", raising=False)
    except Exception:

        class _PatchedSettings:
            ACCESS_SECRET = getattr(settings, "ACCESS_SECRET", "dev-access")
            REFRESH_SECRET = getattr(settings, "REFRESH_SECRET", "dev-refresh")
            JWT_ALG = "HS256"

        monkeypatch.setattr(
            jwt_service, "get_settings", lambda: _PatchedSettings(), raising=True
        )


###### TESTS FOR JWT SERVICE ######
# make_access_token: happy path
def test_make_access_token_and_decode_happy_path():
    '''Test creating and decoding an access token with expected claims.'''
    tok = make_access_token("123", minutes=30)
    payload = decode_token(tok, expected_type="access")
    assert payload["sub"] == "123"
    assert payload["type"] == "access"
    assert payload["aud"] == "your-api"
    assert payload["iss"] == "your-auth"
    assert "jti" in payload and payload["jti"]
    assert "exp" in payload and isinstance(payload["exp"], int)


# decode_token: wrong type => 400
def test_decode_token_wrong_type_raises_400(monkeypatch):
    '''Test that decoding a token with the wrong expected type raises HTTP 400.'''
    settings = jwt_service.get_settings()
    monkeypatch.setattr(settings, "ACCESS_SECRET", "same-secret", raising=False)
    monkeypatch.setattr(settings, "REFRESH_SECRET", "same-secret", raising=False)
    access = make_access_token("1", minutes=10)
    with pytest.raises(HTTPException) as ei:
        decode_token(access, expected_type="refresh")
    assert ei.value.status_code == 400
    assert "Invalid token type" in ei.value.detail


# decode_token: invalid signature / garbage => 401
def test_decode_token_invalid_signature_or_garbage_raises_401():
    '''Test that decoding a token with invalid signature or garbage raises HTTP 401.'''
    with pytest.raises(HTTPException) as ei:
        decode_token("garbage.token.value", expected_type="access")
    assert ei.value.status_code == 401


# decode_token: same secrets but wrong type => 400
def test_decode_token_wrong_type_with_same_secrets_raises_400(monkeypatch):
    '''Test that decoding a token with same secrets but wrong expected type raises HTTP 400.'''
    settings = jwt_service.get_settings()
    monkeypatch.setattr(settings, "ACCESS_SECRET", "same-secret", raising=False)
    monkeypatch.setattr(settings, "REFRESH_SECRET", "same-secret", raising=False)
    access = make_access_token("1", minutes=10)
    with pytest.raises(HTTPException) as ei:
        decode_token(access, expected_type="refresh")
    assert ei.value.status_code == 400
    assert "Invalid token type" in ei.value.detail


# decode_token: different secrets and wrong type => 401 (не зможе верифікувати)
def test_decode_token_wrong_type_with_different_secrets_yields_401():
    '''Test that decoding a token with different secrets and wrong expected type raises HTTP 401.'''
    access = make_access_token("1", minutes=10)
    with pytest.raises(HTTPException) as ei:
        decode_token(access, expected_type="refresh")
    assert ei.value.status_code == 401
