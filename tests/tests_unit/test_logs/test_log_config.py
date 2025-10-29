# tests/test_logs/test_log_config.py
# This file contains tests for the logging configuration and behavior.


###### IMPORT TOOLS ######
import os
import logging
from importlib import reload
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from logging.handlers import RotatingFileHandler
import pytest

import src.logs.log_config as log_config


###### HELPERS ######
def _root_handlers():
    '''Get the list of handlers attached to the root logger.'''
    return logging.getLogger().handlers


def _rotating_handlers():
    '''Get the list of RotatingFileHandler instances attached to the root logger.'''
    return [h for h in _root_handlers() if isinstance(h, RotatingFileHandler)]


def _reset_root_logging():
    '''Remove all handlers from the root logger.'''
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass


##### TEST CONSOLE LOGGING CAPTURED VIA CAPLOG ######
def test_console_logging_captured_via_caplog(caplog):
    '''Test that console logging is captured via caplog.'''
    caplog.set_level(logging.WARNING)
    log_config.logger.warning("console test")
    assert "console test" in caplog.text


### TEST FILE LOGGING WRITES TO FILE ######
@pytest.mark.asyncio
async def test_file_logging_writes_to_file(tmp_path, monkeypatch):
    '''Test that file logging writes to the expected log file.'''
    monkeypatch.setattr(log_config.get_settings(), "APP_ENV", "local")
    log_file_path = os.path.join(str(tmp_path), "app.log")
    monkeypatch.setattr(log_config.get_settings(), "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(log_config.get_settings(), "LOG_FILE", log_file_path)
    _reset_root_logging()
    new_config = reload(log_config)
    file_handlers = [h for h in _root_handlers() if isinstance(h, RotatingFileHandler)]
    assert file_handlers, "RotatingFileHandler не знайдений на root-логері після reload()"
    fh = file_handlers[0]
    new_config.logger.info("hello test")
    try:
        fh.flush()
    except Exception:
        pass
    path = fh.baseFilename
    assert os.path.exists(path), f"Файлу логів немає: {path}"
    data = open(path, "r", encoding="utf-8").read()
    assert "hello test" in data


# check watchfiles logger level is WARNING
def test_watchfiles_logger_level_is_warning():
    '''Test that the watchfiles logger level is set to WARNING.'''
    lg = logging.getLogger("watchfiles")
    assert lg.level == logging.WARNING


# check no duplicate rotating handlers after multiple reloads
def test_no_duplicate_rotating_handlers_after_multiple_reloads(monkeypatch, tmp_path):
    '''Test that no duplicate RotatingFileHandler instances are added after multiple reloads.'''
    monkeypatch.setattr(log_config.get_settings(), "APP_ENV", "local")
    log_file_path = os.path.join(str(tmp_path), "app.log")
    monkeypatch.setattr(log_config.get_settings(), "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(log_config.get_settings(), "LOG_FILE", log_file_path)
    _reset_root_logging()
    reload(log_config)
    first_count = len(_rotating_handlers())
    reload(log_config)
    reload(log_config)
    subsequent_count = len(_rotating_handlers())
    assert first_count == 1, "Was expecting exactly 1 RotatingFileHandler after first reload()"
    assert subsequent_count == 1, "No duplicate RotatingFileHandler after multiple reload()"


# check that LOG_DIR is created if it does not exist
def test_log_dir_is_created(monkeypatch, tmp_path):
    '''Test that the LOG_DIR is created if it does not exist.'''
    log_dir = tmp_path / "logs_should_be_created"
    monkeypatch.setattr(log_config.get_settings(), "LOG_DIR", str(log_dir))
    monkeypatch.setattr(log_config.get_settings(), "LOG_FILE", os.path.join(str(log_dir), "app.log"))
    if log_dir.exists():
        for p in log_dir.iterdir():
            p.unlink()
        log_dir.rmdir()
    assert not log_dir.exists()
    _reset_root_logging()
    reload(log_config)
    assert log_dir.exists() and log_dir.is_dir(), "LOG_DIR must be created if it does not exist"


# check that file handler points to expected path
def test_file_handler_points_to_expected_path(monkeypatch, tmp_path):
    '''Test that the file handler points to the expected log file path.'''
    log_file_path = os.path.join(str(tmp_path), "expected.log")
    monkeypatch.setattr(log_config.get_settings(), "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(log_config.get_settings(), "LOG_FILE", log_file_path)
    _reset_root_logging()
    reload(log_config)
    fhs = _rotating_handlers()
    assert fhs, "RotatingFileHandler має існувати"
    fh = fhs[0]
    expected = log_file_path
    assert fh.baseFilename == expected


# testing exception handlers logging levels
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expected_level_name",
    [
        (404, "WARNING"),
        (307, "INFO"),
    ],
)
async def test_http_exception_handler_logs_level(caplog, status, expected_level_name):
    '''Test that http_exception_handler logs at the expected level based on status code.'''
    caplog.set_level(logging.INFO)
    req = Request({"type": "http", "method": "GET", "path": "/x", "headers": []})
    exc = HTTPException(status_code=status, detail="boom")
    resp = await log_config.http_exception_handler(req, exc)
    assert resp.status_code == status
    records = [
        r for r in caplog.records if r.name == "app" and "HTTPException" in r.getMessage()
    ]
    assert records, "Очікував запис у логах від http_exception_handler"
    assert records[-1].levelname == expected_level_name


# testing validation exception handler logs and returns 422
@pytest.mark.asyncio
async def test_validation_exception_handler_logs_and_returns_422(caplog):
    '''Test that validation_exception_handler logs a warning and returns 422 response.'''
    caplog.set_level(logging.WARNING)
    req = Request({"type": "http", "method": "POST", "path": "/register", "headers": []})
    exc = RequestValidationError(
        errors=[{"type": "value_error", "loc": ("body",), "msg": "Passwords do not match"}]
    )
    exc.body = {"email": "user@example.com", "password": "x", "password_confirm": "y"}
    resp = await log_config.validation_exception_handler(req, exc)
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 422
    msgs = [r.getMessage() for r in caplog.records if r.levelname == "WARNING" and r.name == "app"]
    assert any("422 validation error" in m for m in msgs), "Not found expected warning log message"


# test that file logging appends, not overwrites
@pytest.mark.asyncio
async def test_file_logging_appends_not_overwrites(tmp_path, monkeypatch):
    '''Test that file logging appends to the log file instead of overwriting it.'''
    monkeypatch.setattr(log_config.get_settings(), "APP_ENV", "local")
    log_file_path = os.path.join(str(tmp_path), "append.log")
    monkeypatch.setattr(log_config.get_settings(), "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(log_config.get_settings(), "LOG_FILE", log_file_path)
    _reset_root_logging()
    reload(log_config)
    fh = _rotating_handlers()[0]
    log_config.logger.info("line-1")
    try:
        fh.flush()
    except Exception:
        pass
    log_config.logger.info("line-2")
    try:
        fh.flush()
    except Exception:
        pass
    with open(fh.baseFilename, "r", encoding="utf-8") as f:
        data = f.read()
    assert "line-1" in data and "line-2" in data, "Was expecting both log lines in the file"
