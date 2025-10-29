# ./tests/test_user_auth/test_auth_schemas.py

###### IMPORT TOOLS ######
# global imports
import pytest
from datetime import datetime
from pydantic import ValidationError

# local imports
from src.user_auth.schemas import (
    UserRegister,
    UserOut,
    LoginIn,
    OAuth2LoginOut,
    TokenPair,
    TokenRefreshIn,
    ChangePasswordIn,
    LogoutIn,
    validate_password_rules,
)


###### TESTS ######
def test_validate_password_rules_success():
    """Test that a valid password passes validation (no forbidden symbols)."""
    valid_password = "GoodP!ssw0rd"
    result = validate_password_rules(valid_password)
    assert result == valid_password


@pytest.mark.parametrize(
    "password, expected_error",
    [
        ("lowercase1@", "uppercase letter"),
        ("UPPERCASE1@", "lowercase letter"),
        ("NoDigits!@", "digit"),
        ("NoSpecial123", "special character"),
        ("Invalid@123A", "not allowed symbols"),
    ],
)
def test_validate_password_rules_failures(password, expected_error):
    """Test that invalid passwords raise appropriate ValueError."""
    with pytest.raises(ValueError) as exc_info:
        validate_password_rules(password)
    assert expected_error in str(exc_info.value)


def test_user_register_valid():
    """Test that UserRegister accepts matching valid passwords (no forbidden symbols)."""
    data = {
        "email": "user@example.com",
        "password": "ValidP!ss1",
        "password_confirm": "ValidP!ss1",
    }
    user = UserRegister(**data)
    assert user.email == "user@example.com"
    assert user.password == "ValidP!ss1"


def test_user_register_passwords_do_not_match():
    """Test that UserRegister raises error when passwords do not match (and are otherwise valid)."""
    data = {
        "email": "user@example.com",
        "password": "ValidP!ss1",             # valid password
        "password_confirm": "Mismatch!23",    # valid but different
    }
    with pytest.raises(ValidationError) as exc_info:
        UserRegister(**data)
    assert "Passwords do not match" in str(exc_info.value)


def test_user_out_model_from_attributes():
    """Test that UserOut model correctly maps attributes."""
    data = {
        "id": 1,
        "email": "user@example.com",
        "created_at": datetime(2025, 1, 1, 12, 0, 0),
    }
    user_out = UserOut(**data)
    assert user_out.id == 1
    assert user_out.email == "user@example.com"
    assert isinstance(user_out.created_at, datetime)


def test_login_in_schema():
    """Test that LoginIn validates email and password length (no password rule here)."""
    data = {"email": "user@example.com", "password": "ValidP!ss1"}
    login = LoginIn(**data)
    assert login.email == "user@example.com"
    assert login.password == "ValidP!ss1"


def test_oauth2_login_out_defaults():
    """Test that OAuth2LoginOut uses correct default values."""
    token_data = {"access_token": "abc123"}
    oauth_out = OAuth2LoginOut(**token_data)
    assert oauth_out.token_type == "bearer"
    assert oauth_out.refresh is None
    assert oauth_out.access_token == "abc123"


def test_token_pair_defaults():
    """Test that TokenPair sets correct defaults."""
    data = {"access": "access123", "refresh": "refresh123"}
    pair = TokenPair(**data)
    assert pair.token_type == "bearer"
    assert pair.redirect_url == "/"
    assert pair.access == "access123"
    assert pair.refresh == "refresh123"


def test_token_refresh_in_schema():
    """Test that TokenRefreshIn validates refresh token presence."""
    data = {"refresh": "refresh-token-abc"}
    model = TokenRefreshIn(**data)
    assert model.refresh == "refresh-token-abc"


def test_change_password_in_valid():
    """Test that ChangePasswordIn accepts valid and matching new passwords (no forbidden symbols)."""
    data = {
        "current_password": "OldP!ssw0rd1",
        "new_password": "NewP!ssw0rd1",            # '!' allowed
        "new_password_confirm": "NewP!ssw0rd1",
    }
    result = ChangePasswordIn(**data)
    assert result.new_password == "NewP!ssw0rd1"


@pytest.mark.parametrize(
    "data, expected_error",
    [
        (
            {
                "current_password": "OldP!ssw0rd1",
                "new_password": "NewP!ssw0rd1",            # valid format
                "new_password_confirm": "Mismatch!ssw0rd1", # also valid format but different
            },
            "New password and confirmation do not match",
        ),
        (
            {
                "current_password": "SameP!ss1",
                "new_password": "SameP!ss1",               # identical to current (valid format)
                "new_password_confirm": "SameP!ss1",
            },
            "New password must differ from current password",
        ),
    ],
)
def test_change_password_in_invalid(data, expected_error):
    """Test that ChangePasswordIn raises validation errors for invalid input."""
    with pytest.raises(ValidationError) as exc_info:
        ChangePasswordIn(**data)
    assert expected_error in str(exc_info.value)


def test_logout_in_schema():
    """Test that LogoutIn requires a refresh token."""
    data = {"refresh": "refresh-token-xyz"}
    model = LogoutIn(**data)
    assert model.refresh == "refresh-token-xyz"
