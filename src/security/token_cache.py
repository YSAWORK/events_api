# src/security/token_cache.py
# This module provides a TokenCache class for managing JWT tokens in Redis, including storing, retrieving, and revoking tokens.


###### IMPORT TOOLS ######
# global imports
from __future__ import annotations
from typing import Any, Optional
from datetime import datetime, timezone, timedelta
import json
from uuid import uuid4
from redis.asyncio import Redis

# local imports
from src.config import get_settings
from src.infrastructure.resources import resources
from src.security import jwt_service


###### TOKEN CACHE ######
class TokenCache:
    def __init__(self, redis: Redis):
        self.r = redis
        self.prefix = get_settings().TOKEN_CACHE_PREFIX

    def _key_user_sessions(self, user_id: int | str) -> str:
        '''Key for the set of active refresh token JTIs for a user.'''
        return f"{self.prefix}:user_sessions:{user_id}"

    def _key_access(self, jti: str) -> str:
        '''Key for storing access token payload by its JTI.'''
        return f"{self.prefix}:access:{jti}"

    def _key_refresh(self, jti: str) -> str:
        '''Key for storing refresh token payload by its JTI.'''
        return f"{self.prefix}:refresh:{jti}"

    def _key_revoked(self, jti: str) -> str:
        '''Key for marking a token as revoked by its JTI.'''
        return f"{self.prefix}:revoked:{jti}"

    ###### TTL CALCULATION ######
    @staticmethod
    def _ttl_from_exp(exp: int | float | datetime) -> int:
        """Counts TTL in seconds from `exp` (int/float timestamp or datetime)."""
        now = datetime.now(tz=timezone.utc)
        if isinstance(exp, (int, float)):
            exp_dt = datetime.fromtimestamp(float(exp), tz=timezone.utc)
        else:
            exp_dt = exp
        ttl = int((exp_dt - now).total_seconds())
        return max(ttl, 0)

    ###### TOKEN OPERATIONS ######
    async def register_refresh(
        self,
        user_id: int,
        jti: str,
        payload: dict[str, Any],
        exp: int | float | datetime,
    ) -> None:
        """Register refresh token in cache and link it to user_id."""
        ttl = self._ttl_from_exp(exp)
        if ttl <= 0:
            return
        await self.r.set(self._key_refresh(jti), json.dumps(payload), ex=ttl)
        await self.r.sadd(self._key_user_sessions(user_id), jti)

    async def ttl_of_refresh(self, jti: str) -> int:
        """Get TTL of refresh token by its `jti`."""
        return int(await self.r.ttl(self._key_refresh(jti)))

    async def revoke_refresh(self, jti: str) -> bool:
        """
        Revoke refresh token by its `jti` and mark it as revoked in cache.
        Returns True if the token was found and revoked, False otherwise.
        """
        ttl = await self.ttl_of_refresh(jti)
        if ttl <= 0:
            return False
        await self.r.set(self._key_revoked(jti), "1", ex=ttl)
        await self.r.delete(self._key_refresh(jti))
        return True

    async def revoke_all_user_refresh(self, user_id: int) -> int:
        """
        Revoke all refresh tokens for a given user_id.
        Returns the number of revoked tokens.
        """
        key_set = self._key_user_sessions(user_id)
        jtiset = await self.r.smembers(key_set)
        if not jtiset:
            return 0
        revoked = 0
        for jti in jtiset:
            if await self.revoke_refresh(jti):
                revoked += 1
            await self.r.srem(key_set, jti)
        return revoked

    async def store_access(
        self, jti: str, payload: dict[str, Any], exp: int | float | datetime
    ) -> None:
        """Store access token payload in cache until its `exp`."""
        ttl = self._ttl_from_exp(exp)
        if ttl > 0:
            await self.r.set(self._key_access(jti), json.dumps(payload), ex=ttl)

    async def store_refresh(
        self, jti: str, payload: dict[str, Any], exp: int | float | datetime
    ) -> None:
        """Store refresh token payload in cache until its `exp`."""
        ttl = self._ttl_from_exp(exp)
        if ttl > 0:
            await self.r.set(self._key_refresh(jti), json.dumps(payload), ex=ttl)

    async def get_access(self, jti: str) -> dict[str, Any] | None:
        """Retrieve access token payload from cache by its `jti`."""
        raw = await self.r.get(self._key_access(jti))
        return json.loads(raw) if raw else None

    async def get_refresh(self, jti: str) -> dict[str, Any] | None:
        """Retrieve refresh token payload from cache by its `jti`."""
        raw = await self.r.get(self._key_refresh(jti))
        return json.loads(raw) if raw else None

    async def revoke(self, jti: str, exp: int | float | datetime) -> None:
        """Mark token as revoked in cache until its `exp`."""
        ttl = self._ttl_from_exp(exp)
        if ttl > 0:
            await self.r.set(self._key_revoked(jti), "1", ex=ttl)

    ###### CHECK REVOCATION ######
    async def is_revoked(self, jti: str) -> bool:
        """Check if token is marked as revoked in cache."""
        return bool(await self.r.exists(self._key_revoked(jti)))

    ###### DELETE TOKENS ######
    async def delete_access(self, jti: str) -> None:
        """Delete access token from cache by its `jti`."""
        await self.r.delete(self._key_access(jti))

    async def delete_refresh(self, jti: str) -> None:
        """Delete refresh token from cache by its `jti`."""
        await self.r.delete(self._key_refresh(jti))


###### ISSUE TOKEN ######
async def issue_tokens_for_user(
    user_id: int,
    *,
    access: bool = False,
    refresh: bool = False,
) -> dict[str, Optional[Any]]:
    '''Issue access and/or refresh tokens for a user and store them in cache.'''
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    now = datetime.now(tz=timezone.utc)
    cache = TokenCache(resources.redis)
    if access:
        jti_access = str(uuid4())
        exp_access = now + timedelta(minutes=15)
        access_token = jwt_service.make_access_token(
            sub=str(user_id), jti=jti_access, exp=exp_access, typ="access"
        )
        await cache.store_access(jti_access, {"sub": user_id}, exp_access)
        expires_in = int((exp_access - now).total_seconds())
    if refresh:
        jti_refresh = str(uuid4())
        exp_refresh = now + timedelta(days=1)
        refresh_token = jwt_service.make_refresh_token(
            sub=str(user_id), jti=jti_refresh, exp=exp_refresh, typ="refresh"
        )
        await cache.store_refresh(jti_refresh, {"sub": user_id}, exp_refresh)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": expires_in,
    }
