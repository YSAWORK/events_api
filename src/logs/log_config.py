# src/logs/log_config.py
# logging configuration


###### IMPORT TOOLS ######
# global imports
import os
import logging
from logging.handlers import RotatingFileHandler
from fastapi import Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import (
    request_validation_exception_handler,
    http_exception_handler as fastapi_http_exception_handler,
)

# local imports
from src.config import get_settings


# file-logger
os.makedirs(get_settings().LOG_DIR, exist_ok=True)
file_handler = RotatingFileHandler(
    get_settings().LOG_FILE,
    maxBytes=5 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
)

# console-logger
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(levelname)s | %(name)s | %(message)s")
)

# root-logger
logging.basicConfig(
    level=logging.INFO,
    handlers=[console_handler, file_handler],
)

# module logger
logger = logging.getLogger("app")
logging.getLogger("watchfiles").setLevel(logging.WARNING)


# exception handlers
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    '''Custom handler for 422 validation errors that logs details.'''
    logger.warning(
        "422 validation error on %s %s | errors=%s | body=%s",
        request.method,
        request.url.path,
        exc.errors(),
        getattr(exc, "body", None),
    )
    return await request_validation_exception_handler(request, exc)


# HTTPException handler
async def http_exception_handler(request: Request, exc: HTTPException):
    '''Custom handler for HTTP exceptions that logs details.'''
    level = logger.warning if exc.status_code >= 400 else logger.info
    level(
        "HTTPException %s on %s %s | detail=%s",
        exc.status_code,
        request.method,
        request.url.path,
        exc.detail,
    )
    return await fastapi_http_exception_handler(request, exc)

