# src/user_auth/data_base/crud.py
# This module contains CRUD operations for user management, including user retrieval, creation, and authentication.


###### IMPORT TOOLS ######
# global imports
import logging
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

# local imports
from src.data_base.db import AsyncSession
from src.data_base.models import User
from src.user_auth.utils import get_password_hash
from src.user_auth.schemas import UserRegister
from src.infrastructure.resources import resources
from src.config import get_settings


###### LOGGER ######
logger = logging.getLogger("app.data_base.crud")


###### CHECK USER BY EMAIL ######
async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    '''Fetch a user by email if not deleted.'''
    res = await db.execute(
        select(User).where(User.email == email,).limit(1)
    )
    return res.scalar_one_or_none()


###### CREATE USER ######
async def create_user(db: AsyncSession, data: UserRegister) -> User:
    '''Create a new user with hashed password.'''
    user = User(email=data.email, hashed_password=get_password_hash(data.password))
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
        return user
    except IntegrityError:
        await db.rollback()
        raise
    except SQLAlchemyError:
        await db.rollback()
        raise


###### GET CURRENT USER ######
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(resources.get_session),
) -> User:
    '''Decode JWT token and fetch the current user.'''
    cred_exc = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            get_settings().ACCESS_SECRET,
            algorithms=[get_settings().JWT_ALG],
            audience=get_settings().JWT_AUDIENCE,
            issuer=get_settings().JWT_ISSUER,
            options={"leeway": 30},
        )
        user_id = payload.get("sub")
        if not user_id:
            raise cred_exc
    except JWTError:
        raise cred_exc

    res = await db.execute(select(User).where(User.id == int(user_id)))
    user = res.scalar_one_or_none()
    if not user:
        raise cred_exc
    return user


###### GET CURRENT USER OPTIONAL ######
oauth2_optional = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)

# BenchmarkUser for benchmarking purposes
class BenchmarkUser:
    id = 0
    email = "benchmark@local"
    roles = ["benchmark"]

# get current user or return BenchmarkUser if in benchmark mode
async def benchmark_or_auth(
        request: Request,
        token: str | None = Depends(oauth2_optional),
        db: AsyncSession = Depends(resources.get_session),
) -> User | BenchmarkUser:
    if getattr(request.state, "is_benchmark", False):
        return BenchmarkUser()
    return await get_current_user(token, db)
