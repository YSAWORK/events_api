# src/user_auth/jwt_service.py
# This module provides JWT token creation, decoding, validation, and revocation services.


###### IMPORT TOOLS ######
# global imports
import jwt
from jwt import exceptions
from fastapi import HTTPException
from typing import Literal, Optional, List
from datetime import datetime, timedelta, timezone

# local imports
from src.config import get_settings


###### HELPERS ######
# current UTC time
def _now_utc() -> datetime:
    '''Get the current UTC time as a timezone-aware datetime object.'''
    return datetime.now(timezone.utc)


# common JWT claims
def _jwt_common_claims(sub: str, token_type: str, jti: str) -> dict:
    '''Generate common JWT claims for a token.'''
    now = _now_utc()
    return {
        "sub": sub,
        "type": token_type,
        "jti": jti,
        "iat": int(now.timestamp()),
        "iss": "your-auth",
        "aud": "auth_api",
    }


###### MAKE JWT TOKEN ######
# access token
def make_access_token(
    sub: str,
    jti: Optional[str] = None,
    exp: Optional[datetime] = None,
    minutes: Optional[int] = 15,
    typ: str = "access",
) -> List:
    '''Create a JWT access token with specified claims and expiration.'''
    claims = _jwt_common_claims(sub, typ, jti)
    if exp is None:
        exp = _now_utc() + timedelta(minutes=minutes)
    claims["exp"] = int(exp.timestamp())
    return jwt.encode(
        claims, get_settings().ACCESS_SECRET, algorithm=get_settings().JWT_ALG
    )


# create and store refresh token
def make_refresh_token(
    sub: str,
    jti: Optional[str] = None,
    exp: Optional[datetime] = None,
    days: Optional[int] = 1,
    typ: str = "refresh",
) -> List:
    '''Create a JWT refresh token with specified claims and expiration.'''
    claims = _jwt_common_claims(sub, typ, jti)
    if exp is None:
        exp = _now_utc() + timedelta(days=days or 1)
    claims["exp"] = int(exp.timestamp())
    return jwt.encode(
        claims, get_settings().REFRESH_SECRET, algorithm=get_settings().JWT_ALG
    )


###### DECODE JWT TOKEN ######
def decode_token(token: str, *, expected_type: Literal["access", "refresh"]) -> dict:
    secret = (
        get_settings().ACCESS_SECRET
        if expected_type == "access"
        else get_settings().REFRESH_SECRET
    )
    '''Decode and validate a JWT token, ensuring it matches the expected type.'''
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="your-api",
            issuer="your-auth",
            options={"require": ["exp", "sub", "type", "jti"]},
        )
    except exceptions.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail="Invalid or expired token.") from e
    if payload.get("type") != expected_type:
        raise HTTPException(status_code=400, detail="Invalid token type.")
    return payload
