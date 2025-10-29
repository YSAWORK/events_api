# src/user_auth/schemas.py
# This module contains the Pydantic schemas for user authentication and management.


###### IMPORT TOOLS ######
# global imports
import re
from datetime import datetime
from pydantic import (
    BaseModel,
    EmailStr,
    constr,
    field_validator,
    model_validator,
    ConfigDict,
    Field,
)


# ---------- password rules ----------
def validate_password_rules(value: str) -> str:
    """Validate password against defined rules."""
    if not re.search(r"[A-Z]", value):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", value):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"[0-9]", value):
        raise ValueError("Password must contain at least one digit")
    if not re.search(r"[^\w]", value):
        raise ValueError("Password must contain at least one special character")
    if any(c in value for c in ["@", '"', "'", "<", ">"]):
        raise ValueError("Password contain not allowed symbols (@, \", ', <, >)")
    return value


# ---------- register ----------
class UserRegister(BaseModel):
    """Schema for user registration input."""
    email: EmailStr
    password: constr(min_length=8, max_length=24)
    password_confirm: str

    @field_validator("password", mode="after")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_rules(value)

    @model_validator(mode="after")
    def check_passwords_match(self):
        """Ensure password and confirmation match."""
        if self.password != self.password_confirm:
            raise ValueError("Passwords do not match")
        return self


# ---------- user out ----------
class UserOut(BaseModel):
    """Schema for user output after registration."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    created_at: datetime


# ---------- login ----------
class LoginIn(BaseModel):
    """Schema for user login input."""
    email: EmailStr
    password: constr(min_length=8, max_length=24)


# ---------- OAuth2 login ----------
class OAuth2LoginOut(BaseModel):
    """Schema for OAuth2 login output."""
    access_token: str
    token_type: str = "bearer"
    refresh: str | None = None


# ---------- tokens ----------
class TokenPair(BaseModel):
    """Schema for access and refresh token pair."""
    access: str
    refresh: str
    token_type: str = "bearer"
    redirect_url: str | None = "/"


class TokenRefreshIn(BaseModel):
    """Schema for refresh token input."""
    model_config = ConfigDict(
        json_schema_extra={"example": {"refresh": "<YOUR_REFRESH_JWT_HERE>"}}
    )
    refresh: str = Field(..., description="Refresh JWT")


# ---------- change password ----------
class ChangePasswordIn(BaseModel):
    """Schema for changing user password."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "current_password": "<YOUR_CURRENT_PASSWORD_HERE>",
                "new_password": "<YOUR_NEW_PASSWORD_HERE>",
                "new_password_confirm": "<YOUR_NEW_PASSWORD_CONFIRM_HERE>",
            }
        }
    )
    current_password: constr(min_length=8, max_length=24)
    new_password: constr(min_length=8, max_length=24)
    new_password_confirm: str

    @field_validator("new_password", mode="after")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        """Validate new password against defined rules."""
        return validate_password_rules(value)

    @model_validator(mode="after")
    def check_passwords_match(self):
        """Ensure new password and confirmation match, and differ from current password."""
        if self.new_password != self.new_password_confirm:
            raise ValueError("New password and confirmation do not match")
        if self.new_password == self.current_password:
            raise ValueError("New password must differ from current password")
        return self


# ---------- logout ----------
class LogoutIn(BaseModel):
    """Schema for logout input."""
    refresh: str
