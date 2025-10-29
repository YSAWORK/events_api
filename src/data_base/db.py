# src/data_base/db.py
# This module sets up the asynchronous database connection and session management using SQLAlchemy.


###### IMPORT TOOLS ######
# global imports
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

# local imports
from src.config import get_settings


###### DATABASE URL ######
DATABASE_URL = get_settings().USER_DB_URL

###### CREATE ASYNC ENGINE ######
engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)

###### CREATE ASYNC SESSION MAKER ######
AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


###### BASE CLASS FOR MODELS ######
class Base(DeclarativeBase):
    __abstract__ = True
