# ./tests/test_user_auth/test_auth_utils.py

###### IMPORT TOOLS ######
# global imports
import pytest
from fastapi import HTTPException

# local imports
from src.user_auth.utils import (
    get_password_hash,
    verify_password,
    check_authorization,
)


###### TESTS ######
def test_get_password_hash_returns_bcrypt_hash():
    """Test that get_password_hash returns a valid bcrypt hash string."""
    password = "MySecureP@ssw0rd"
    hashed = get_password_hash(password)
    assert isinstance(hashed, str)
    assert hashed != password
    assert hashed.startswith("$2"), f"Unexpected bcrypt prefix: {hashed[:4]}"


def test_verify_password_success():
    """Test that verify_password returns True for a correct password."""
    password = "Secret123!"
    hashed = get_password_hash(password)
    assert verify_password(password, hashed) is True


def test_verify_password_failure_wrong_password():
    """Test that verify_password returns False for an incorrect password."""
    password = "correct_password"
    hashed = get_password_hash(password)
    assert verify_password("wrong_password", hashed) is False


def test_check_authorization_allows_same_user(caplog):
    """Test that check_authorization does not raise an error for the same user."""
    caplog.clear()
    check_authorization(user_id=10, current_user_id=10)
    assert not any(rec.levelname == "WARNING" for rec in caplog.records)


def test_check_authorization_forbidden_and_logs_warning(caplog):
    """Test that check_authorization raises 403 and logs a warning for unauthorized access."""
    caplog.clear()
    with pytest.raises(HTTPException) as exc_info:
        check_authorization(user_id=1, current_user_id=2)
    exception = exc_info.value
    assert exception.status_code == 403
    assert exception.detail == "You can only access your own data."
    warnings = [rec for rec in caplog.records if rec.levelname == "WARNING"]
    assert warnings, "Expected a WARNING log when unauthorized access is checked"
    assert "attempted to access User ID 1 data" in warnings[0].msg
