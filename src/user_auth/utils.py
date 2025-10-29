# src/user_auth/utils.py
# this module contains utility functions for user authentication and management


####### IMPORT TOOLS #######
# global imports
import logging
from passlib.context import CryptContext
from fastapi import HTTPException


###### LOGGER ######
logger = logging.getLogger("app.user_profile.utils")

# set up password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


###### PASSWORD HASHING FUNCTION ######
# to hash a plain password
def get_password_hash(password: str) -> str:
    '''Hash a plain password using bcrypt.'''
    return pwd_context.hash(password)


# to verify a plain password against a hashed password
def verify_password(plain_password: str, hashed_password: str) -> bool:
    '''Verify a plain password against a hashed password.'''
    return pwd_context.verify(plain_password, hashed_password)


###### CHECK AUTHORIZATION ######
def check_authorization(user_id: int, current_user_id: int) -> None:
    '''Ensure users can only access their own data.'''
    if user_id != current_user_id:
        logger.warning(
            f"User ID {current_user_id} attempted to access User ID {user_id} data."
        )
        raise HTTPException(
            status_code=403, detail="You can only access your own data."
        )