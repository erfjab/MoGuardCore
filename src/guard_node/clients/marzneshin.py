from enum import Enum

from typing import Optional
from aiohttp import ClientSession
from datetime import datetime
from pydantic import BaseModel
from .base import BaseClient


class MarzneshinToken(BaseModel):
    access_token: str
    is_sudo: bool
    token_type: str = "bearer"


class MarzneshinAdmin(BaseModel):
    username: str
    is_sudo: bool
    enabled: bool = True

    @property
    def is_active(self) -> bool:
        return self.is_sudo and self.enabled


class UserExpireStrategy(str, Enum):
    NEVER = "never"
    FIXED_DATE = "fixed_date"
    START_ON_FIRST_USE = "start_on_first_use"


class MarzneshinUserResponse(BaseModel):
    username: str
    key: Optional[str]
    is_active: bool
    data_limit: Optional[int]
    lifetime_used_traffic: Optional[int] = None
    lifetime_used_traffic: Optional[int] = None
    owner_username: Optional[str]
    expire_strategy: UserExpireStrategy
    expire_date: Optional[datetime]
    used_traffic: Optional[int] = None
    usage_duration: Optional[int]
    activation_deadline: Optional[datetime]
    subscription_url: str
    service_ids: list[int]
    enabled: bool
    created_at: datetime

    @property
    def data_left(self) -> int:
        if not self.data_limit:
            return 0
        if not self.used_traffic:
            return self.data_limit
        data_left = int(self.data_limit - self.used_traffic)
        if data_left <= 0:
            return 1024
        return data_left


class MarzneshinServiceResponce(BaseModel):
    id: int
    name: str | None
    inbound_ids: list[int]
    user_ids: list[int]


class MarzneshinClient(BaseClient):
    def __init__(self, host: str, session: Optional[ClientSession] = None):
        super().__init__(host, session)

    async def generate_access_token(self, *, username: str, password: str) -> Optional[MarzneshinToken]:
        data = {
            "grant_type": "password",
            "username": username,
            "password": password,
            "scope": "",
            "client_id": "",
            "client_secret": "",
        }
        return await self.post(
            endpoint="/api/admins/token",
            data=data,
            response_model=MarzneshinToken,
        )

    async def get_admin(self, *, username: str, access: str) -> Optional[MarzneshinAdmin]:
        return await self.get(
            endpoint=f"/api/admins/{username}",
            access_token=access,
            response_model=MarzneshinAdmin,
        )

    async def get_configs(self, *, access: str) -> Optional[list[MarzneshinServiceResponce]]:
        services = await self.get(endpoint="/api/services", access_token=access)
        if not services:
            return False
        return [MarzneshinServiceResponce(**service) for service in services["items"]]

    async def get_user(self, *, username: str, access: str) -> Optional[MarzneshinUserResponse]:
        return await self.get(
            endpoint=f"/api/users/{username}",
            access_token=access,
            response_model=MarzneshinUserResponse,
        )

    async def get_users(
        self, *, access: str, size: int, page: int, usernames: Optional[list[str]] = None, activate: Optional[bool] = None
    ) -> Optional[list[MarzneshinUserResponse]]:
        params = {
            "page": page,
            "size": size,
        }
        if usernames:
            params["username"] = usernames
        if activate is not None:
            params["enabled"] = "true" if activate else "false"
        users = await self.get(
            endpoint="/api/users",
            params=params,
            access_token=access,
        )
        if users is False:
            return None
        if not users or "items" not in users:
            return []
        return [MarzneshinUserResponse(**user) for user in users["items"]]

    async def create_user(self, data: dict, access: str) -> Optional[MarzneshinUserResponse]:
        return await self.post(
            endpoint="/api/users",
            access_token=access,
            data=data,
            response_model=MarzneshinUserResponse,
        )

    async def update_user(self, *, username: str, data: dict, access: str) -> Optional[MarzneshinUserResponse]:
        return await self.put(
            endpoint=f"/api/users/{username}",
            access_token=access,
            data=data,
            response_model=MarzneshinUserResponse,
        )

    async def remove_user(self, *, username: str, access: str) -> bool:
        return await self.delete(
            endpoint=f"/api/users/{username}",
            access_token=access,
        )

    async def activate_user(self, *, username: str, access: str) -> Optional[MarzneshinUserResponse]:
        return await self.post(
            endpoint=f"/api/users/{username}/enable",
            access_token=access,
            response_model=MarzneshinUserResponse,
        )

    async def deactivate_user(self, *, username: str, access: str) -> Optional[MarzneshinUserResponse]:
        return await self.post(
            endpoint=f"/api/users/{username}/disable",
            access_token=access,
            response_model=MarzneshinUserResponse,
        )

    async def reset_user(self, *, username: str, access: str) -> Optional[MarzneshinUserResponse]:
        return await self.post(
            endpoint=f"/api/users/{username}/reset",
            access_token=access,
            response_model=MarzneshinUserResponse,
        )

    async def revoke_user(self, *, username: str, access: str) -> Optional[MarzneshinUserResponse]:
        return await self.post(
            endpoint=f"/api/users/{username}/revoke_sub",
            access_token=access,
            response_model=MarzneshinUserResponse,
        )

    async def get_users_count(self, *, access: str) -> Optional[int]:
        result = await self.get(
            endpoint="/api/system/stats/users",
            access_token=access,
        )
        if not result:
            return None
        return int(result.get("total"))
