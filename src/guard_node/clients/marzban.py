from enum import Enum
from datetime import datetime
from typing import Optional, Dict, List
from aiohttp import ClientSession
from pydantic import BaseModel
from .base import BaseClient


class MarzbanToken(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MarzbanUserStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    LIMITED = "limited"
    EXPIRED = "expired"
    ONHOLD = "on_hold"


class MarzbanAdmin(BaseModel):
    username: str
    is_sudo: bool


class MarzbanUserResponse(BaseModel):
    username: Optional[str] = None
    proxies: Optional[Dict[str, dict]] = {}
    expire: Optional[int] = None
    data_limit: Optional[int] = None
    inbounds: Optional[Dict[str, List[str]]] = None
    on_hold_expire_duration: Optional[int] = None
    status: MarzbanUserStatus = MarzbanUserStatus.ACTIVE
    used_traffic: Optional[int] = None
    lifetime_used_traffic: Optional[int] = 0
    subscription_url: Optional[str] = None
    admin: Optional[MarzbanAdmin] = None
    links: list[str] = []
    created_at: datetime

    @property
    def enabled(self) -> bool:
        return self.status != MarzbanUserStatus.DISABLED

    @property
    def is_active(self) -> bool:
        return self.status in [MarzbanUserStatus.ACTIVE, MarzbanUserStatus.ONHOLD]

    @property
    def data_left(self) -> int:
        if not self.data_limit:
            return 0
        if not self.used_traffic:
            return self.data_limit
        return self.data_limit - self.used_traffic


class MarzbanProxyTypes(str, Enum):
    VMess = "vmess"
    VLESS = "vless"
    Trojan = "trojan"
    Shadowsocks = "shadowsocks"


class MarzbanProxyInbound(BaseModel):
    tag: str
    protocol: MarzbanProxyTypes


class MarzbanClient(BaseClient):
    def __init__(self, host: str, session: Optional[ClientSession] = None):
        super().__init__(host, session)

    async def generate_access_token(self, *, username: str, password: str) -> Optional[MarzbanToken]:
        data = {
            "grant_type": "password",
            "username": username,
            "password": password,
            "scope": "",
            "client_id": "",
            "client_secret": "",
        }
        return await self.post(
            endpoint="/api/admin/token",
            data=data,
            response_model=MarzbanToken,
        )

    async def get_admin(self, *, username: str, access: str) -> Optional[MarzbanAdmin]:
        return await self.get(
            endpoint=f"/api/admin/{username}",
            access_token=access,
            response_model=MarzbanAdmin,
        )

    async def get_configs(self, *, access: str) -> Optional[list[MarzbanProxyInbound]]:
        inbounds: dict = await self.get(endpoint="/api/inbounds", access_token=access)
        if not inbounds:
            return None
        return [
            MarzbanProxyInbound(**inbound)
            for inbound_list in inbounds.values()
            for inbound in (inbound_list if isinstance(inbound_list, list) else [inbound_list])
        ]

    async def get_user(self, *, username: str, access: str) -> Optional[MarzbanUserResponse]:
        return await self.get(
            endpoint=f"/api/user/{username}",
            access_token=access,
            response_model=MarzbanUserResponse,
        )

    async def get_users(
        self, *, access: str, size: int, page: int, usernames: Optional[list[str]] = None, activate: Optional[bool] = None
    ) -> Optional[list[MarzbanUserResponse]]:
        params = {
            "offset": ((page - 1) * size),
            "limit": size,
        }
        if usernames:
            params["username"] = usernames
        if activate is not None:
            params["status"] = "active" if activate else "disabled"
        users = await self.get(
            endpoint="/api/users",
            params=params,
            access_token=access,
        )
        if users is False:
            return None
        if not users or "users" not in users:
            return []
        return [MarzbanUserResponse(**user) for user in users["users"]]

    async def create_user(self, data: dict, access: str) -> Optional[MarzbanUserResponse]:
        return await self.post(
            endpoint="/api/user",
            access_token=access,
            data=data,
            response_model=MarzbanUserResponse,
        )

    async def update_user(self, *, username: str, data: dict, access: str) -> Optional[MarzbanUserResponse]:
        return await self.put(
            endpoint=f"/api/user/{username}",
            access_token=access,
            data=data,
            response_model=MarzbanUserResponse,
        )

    async def remove_user(self, *, username: str, access: str) -> bool:
        return await self.delete(
            endpoint=f"/api/user/{username}",
            access_token=access,
        )

    async def activate_user(self, *, username: str, access: str) -> Optional[MarzbanUserResponse]:
        return await self.put(
            endpoint=f"/api/user/{username}",
            access_token=access,
            data={"status": "active"},
            response_model=MarzbanUserResponse,
        )

    async def deactivate_user(self, *, username: str, access: str) -> Optional[MarzbanUserResponse]:
        return await self.put(
            endpoint=f"/api/user/{username}",
            access_token=access,
            data={"status": "disabled"},
            response_model=MarzbanUserResponse,
        )

    async def reset_user(self, *, username: str, access: str) -> Optional[MarzbanUserResponse]:
        return await self.post(
            endpoint=f"/api/user/{username}/reset",
            access_token=access,
            response_model=MarzbanUserResponse,
        )

    async def revoke_user(self, *, username: str, access: str) -> Optional[MarzbanUserResponse]:
        return await self.post(
            endpoint=f"/api/user/{username}/revoke_sub",
            access_token=access,
            response_model=MarzbanUserResponse,
        )

    async def get_users_count(self, *, access: str) -> Optional[int]:
        result = await self.get(
            endpoint="/api/system",
            access_token=access,
        )
        if not result:
            return None
        return int(result.get("total_user"))
