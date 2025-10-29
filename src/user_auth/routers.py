# src/user_auth/routers.py
# This module contains the FastAPI routes for user authentication and management.


###### IMPORT TOOLS ######
# global imports
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from starlette.responses import Response
from fastapi_limiter.depends import RateLimiter

# local imports
from src.security.token_cache import TokenCache, issue_tokens_for_user
from src.user_auth import schemas
from src.data_base.crud import get_user_by_email, create_user, get_current_user
from src.data_base.db import AsyncSession
from src.data_base.models import User
from src.security.jwt_service import (
    decode_token,
)
from src.user_auth.schemas import LogoutIn
from src.user_auth.utils import verify_password, get_password_hash, check_authorization
from src.infrastructure.resources import resources
from src.infrastructure.metrics import record_event


###### LOGGER ######
logger = logging.getLogger("app.user_auth.routers")


###### CREATE ROUTER ######
router = APIRouter(prefix="/auth")


###### REGISTER ######
@router.post(
    "/register",
    response_model=schemas.UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RateLimiter(times=5, seconds=60))],
)
async def api_register(
    payload: schemas.UserRegister, db: AsyncSession = Depends(resources.get_session)
):
    '''Register a new user.'''
    if await get_user_by_email(db, str(payload.email)):
        raise HTTPException(
            status_code=409, detail="User with this email already exists."
        )
    try:
        user = await create_user(db, payload)
        logger.info(f"User registered: {user.email} | ID {user.id}")
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="User with this email already exists."
        )
    record_event({"name": "auth_register"})
    return user


###### LOGIN ######
@router.post(
    "/login",
    response_model=schemas.TokenPair,
    dependencies=[Depends(RateLimiter(times=5, seconds=60))],
)
async def api_login(
    payload: schemas.LoginIn, db: AsyncSession = Depends(resources.get_session)
):
    '''Authenticate user and issue tokens.'''
    user = await get_user_by_email(db, str(payload.email))
    if not user or not verify_password(payload.password, str(user.hashed_password)):
        raise HTTPException(status_code=401, detail="Wrong password or email")
    tokens = await issue_tokens_for_user(int(user.id), access=True, refresh=True)
    logger.info(f"User ID {user.id} login successful.")
    record_event({"name": "auth_login"})
    return schemas.TokenPair(
        access=tokens["access_token"], refresh=tokens["refresh_token"]
    )


###### OAUTH2 LOGIN ######
@router.post("/token", response_model=schemas.OAuth2LoginOut)
async def issue_token(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(resources.get_session),
):
    '''OAuth2 password flow login to issue access token.'''
    user = await get_user_by_email(db, form.username.strip().lower())
    if not user or not verify_password(form.password, str(user.hashed_password)):
        raise HTTPException(status_code=401, detail="Невірний email або пароль.")
    tokens = await issue_tokens_for_user(int(user.id), access=True, refresh=False)
    return {"access_token": tokens["access_token"], "token_type": tokens["token_type"]}


###### REFRESH TOKEN ######
@router.post("/{user_id}/refresh", response_model=schemas.TokenPair)
async def api_refresh(
    payload: schemas.TokenRefreshIn = Body(...),
):
    '''Refresh access token using a valid refresh token.'''
    payload = decode_token(payload.refresh, expected_type="refresh")
    jti = payload["jti"]
    sub = payload["sub"]
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    cache = TokenCache(resources.redis)
    if await cache.is_revoked(jti):
        raise HTTPException(status_code=401, detail="Refresh token revoked")
    if not await cache.get_refresh(jti):
        raise HTTPException(status_code=401, detail="Refresh token invalid/expired")
    new_tokens = await issue_tokens_for_user(int(sub), access=True, refresh=True)
    await cache.revoke(jti, exp)
    logger.info(f"Token User ID {sub} refresh successful.")
    return schemas.TokenPair(
        access=new_tokens["access_token"], refresh=new_tokens["refresh_token"]
    )


###### LOGOUT ######
@router.post("/{user_id}/logout", status_code=status.HTTP_204_NO_CONTENT)
async def api_logout(
    user_id: int,
    payload: LogoutIn = Body(...),
    current_user: User = Depends(get_current_user),
):
    '''Logout user by revoking the provided refresh token.'''
    check_authorization(user_id, int(current_user.id))
    try:
        data = decode_token(payload.refresh, expected_type="refresh")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if data.get("type") != "refresh":
        raise HTTPException(status_code=400, detail="Invalid token type")
    token_sub = data.get("sub")
    jti = data.get("jti")
    exp = data.get("exp")
    if not token_sub or not jti or not exp:
        raise HTTPException(status_code=400, detail="Malformed refresh token")
    cache = TokenCache(resources.redis)
    if await cache.is_revoked(jti):
        raise HTTPException(
            status_code=409, detail="Session already closed or not found"
        )
    if not await cache.get_refresh(jti):
        raise HTTPException(
            status_code=409, detail="Session already closed or not found"
        )
    await cache.revoke(jti, exp)
    await cache.delete_refresh(jti)
    logger.info(f"User ID {token_sub} logged out successfully.")
    record_event({"name": "auth_logout"})


###### CHANGE PASSWORD ######
@router.post("/{user_id}/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def api_change_password(
    user_id: int,
    payload: schemas.ChangePasswordIn,
    db: AsyncSession = Depends(resources.get_session),
    current_user: User = Depends(get_current_user),
):
    '''Change user's password after verifying current password.'''
    check_authorization(user_id, int(current_user.id))
    user = await db.get(User, int(current_user.id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if not verify_password(payload.current_password, str(user.hashed_password)):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=400, detail="New password must differ from current password."
        )
    user.hashed_password = get_password_hash(payload.new_password)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=500, detail="Could not change password due to a database error."
        )
    cache = TokenCache(resources.redis)
    await cache.revoke_all_user_refresh(int(current_user.id))
    logger.info(f"User ID {current_user.id} changed password successfully.")
    record_event({"name": "auth_change_password"})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
