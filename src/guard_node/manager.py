from typing import Optional
import httpx
from aiohttp import ClientSession, TCPConnector, ClientTimeout
from src.db import Node, NodeCategory, Subscription
from src.db.core import GetDB
from src.config import logger
from src.utils.key import gen_uuid, gen_password
from src.utils.configs import get_configs as get_cached_configs
from .clients import MarzbanClient, MarzneshinClient, RustneshinClient
from .clients.marzban import MarzbanUserResponse, MarzbanProxyInbound
from .clients.marzneshin import MarzneshinUserResponse, MarzneshinServiceResponce
from .clients.rustneshin import RustneshinUserResponse, RustneshinServiceResponse


class GuardNodeManagerCore:
    def __init__(self):
        self._session: Optional[ClientSession] = None

    @property
    def session(self) -> ClientSession:
        if self._session is None or self._session.closed:
            connector = TCPConnector(ssl=False, limit=200, limit_per_host=50, ttl_dns_cache=300, enable_cleanup_closed=True)
            self._session = ClientSession(connector=connector, timeout=ClientTimeout(total=30))
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _generate_client(self, node: Node) -> MarzbanClient | MarzneshinClient | RustneshinClient | None:
        match node.category:
            case NodeCategory.marzban:
                return MarzbanClient(node.host, session=self.session)
            case NodeCategory.marzneshin:
                return MarzneshinClient(node.host, session=self.session)
            case NodeCategory.rustneshin:
                return RustneshinClient(node.host, session=self.session)
            case _:
                return None

    def _generate_expire(self, node: Node) -> dict:
        data = {}
        match node.category:
            case NodeCategory.marzban:
                data["status"] = "active"
                data["expire"] = 0
            case NodeCategory.marzneshin | NodeCategory.rustneshin:
                data["expire_strategy"] = "never"
        return data

    def _generate_guard_configs(
        self,
        data: dict,
        configs: list[MarzbanProxyInbound | MarzneshinServiceResponce | RustneshinServiceResponse],
        node: Node,
        access_key: str = "guard",
        user: MarzbanUserResponse | MarzneshinUserResponse | RustneshinUserResponse | None = None,
    ) -> dict | None:
        """Generate configs for guard user (no subscription required)"""
        match node.category:
            case NodeCategory.marzban:
                if user:
                    current_proxies = user.proxies
                    current_inbounds = user.inbounds
                uuid = gen_uuid(access_key)
                password = gen_password(access_key)
                proxies = {}
                inbounds = {}
                for config in configs:
                    proxies[config.protocol] = self._generate_proxy_configs(
                        uuid=uuid, password=password, protocol=config.protocol
                    )
                    if config.protocol in inbounds:
                        inbounds[config.protocol].append(config.tag)
                    else:
                        inbounds[config.protocol] = [config.tag]
                data["proxies"] = proxies
                data["inbounds"] = inbounds
                if user:
                    if current_proxies == proxies or current_inbounds == inbounds:
                        return None
            case NodeCategory.marzneshin | NodeCategory.rustneshin:
                data["service_ids"] = [config.id for config in configs]
                if user:
                    if user.service_ids == data["service_ids"]:
                        return None
        return data

    def _generate_configs(
        self,
        sub: Subscription,
        data: dict,
        configs: list[MarzbanProxyInbound | MarzneshinServiceResponce | RustneshinServiceResponse],
        node: Node,
    ) -> dict:
        match node.category:
            case NodeCategory.marzban:
                uuid = gen_uuid(sub.access_key)
                password = gen_password(sub.access_key)
                proxies = {}
                inbounds = {}
                for config in configs:
                    proxies[config.protocol] = self._generate_proxy_configs(
                        uuid=uuid, password=password, protocol=config.protocol
                    )
                    if config.protocol in inbounds:
                        inbounds[config.protocol].append(config.tag)
                    else:
                        inbounds[config.protocol] = [config.tag]
                data["proxies"] = proxies
                data["inbounds"] = inbounds
            case NodeCategory.marzneshin | NodeCategory.rustneshin:
                data["service_ids"] = [config.id for config in configs]
        return data

    def _generate_proxy_configs(self, uuid: str, password: str, protocol: str) -> dict:
        match protocol:
            case "vmess":
                return {"id": uuid}
            case "vless":
                return {"flow": "", "id": uuid}
            case "trojan":
                return {"password": password}
            case "shadowsocks":
                return {"password": password, "method": "chacha20-ietf-poly1305"}
            case _:
                logger.warning(f"Unknown protocol {protocol} for Marzban node.")
                return {}

    def _generate_sync_configs(
        self,
        sub: Subscription,
        data: dict,
        should: list[MarzbanProxyInbound | MarzneshinServiceResponce | RustneshinServiceResponse],
        current: MarzbanUserResponse | MarzneshinUserResponse | RustneshinUserResponse | None,
        node: Node,
    ) -> Optional[dict]:
        uuid = gen_uuid(sub.access_key)
        password = gen_password(sub.access_key)
        match node.category:
            case NodeCategory.marzban:
                current_proxies = current.proxies
                current_inbounds = current.inbounds
                proxies = {}
                inbounds = {}
                for config in should:
                    protocol = config.protocol
                    if protocol.value in current_proxies:
                        if sub.changed:
                            proxies[protocol.value] = self._generate_proxy_configs(
                                uuid=uuid, password=password, protocol=protocol
                            )
                        else:
                            proxies[protocol.value] = current_proxies[protocol.value]
                    else:
                        proxies[protocol.value] = self._generate_proxy_configs(uuid=uuid, password=password, protocol=protocol)
                    if protocol.value in inbounds:
                        inbounds[protocol.value].append(config.tag)
                    else:
                        inbounds[protocol.value] = [config.tag]
                if inbounds != current_inbounds or proxies != current_proxies:
                    logger.error(f"Syncing configs for subscription {sub.server_key} on node {node.remark}")
                    logger.error(f"Current inbounds: {current_inbounds}, should inbounds: {inbounds}")
                    logger.error(f"Current proxies: {current_proxies}, should proxies: {proxies}")
                    data["proxies"] = proxies
                    data["inbounds"] = inbounds
                    return data
            case NodeCategory.marzneshin | NodeCategory.rustneshin:
                should = [config.id for config in should]
                if current.service_ids != should:
                    data["service_ids"] = should
                    return data
        return None

    async def register(self, username: str, password: str, host: str, category: NodeCategory) -> Optional[str]:
        client = self._generate_client(node=Node(host=host, category=category))
        if not client:
            return None
        token_response = await client.generate_access_token(username=username, password=password)
        return token_response.access_token if token_response else None

    async def get_configs(self, node: Node) -> Optional[dict]:
        client = self._generate_client(node=node)
        if not client:
            return None
        return await client.get_configs(access=node.access)

    async def create_subscription(
        self,
        sub: Subscription,
        node: Optional[Node] = None,
        configs: list[MarzbanProxyInbound | MarzneshinServiceResponce | RustneshinServiceResponse] = None,
    ) -> None:
        for node in sub.nodes if not node else [node]:
            data = self._generate_expire(node=node)
            data["username"] = sub.server_key
            data["data_limit"] = 0
            if configs is None:
                configs = get_cached_configs(node.id)
                if not configs:
                    configs = await self.get_configs(node=node)
            if not configs:
                continue
            data = self._generate_configs(sub=sub, data=data, configs=configs, node=node)
            client = self._generate_client(node=node)
            if not client:
                continue
            if node.category in [NodeCategory.marzneshin, NodeCategory.rustneshin]:
                data["key"] = sub.access_key
            await client.create_user(data=data, access=node.access)
            configs = None

    async def revoke_subscription(self, sub: Subscription, node: Optional[Node] = None) -> None:
        for node in sub.nodes if not node else [node]:
            client = self._generate_client(node=node)
            if not client:
                continue
            await client.remove_user(username=sub.server_key, access=node.access)
            await self.create_subscription(sub=sub, node=node)

    async def activate_subscription(self, sub: Subscription, node: Optional[Node] = None) -> None:
        for node in sub.nodes if not node else [node]:
            client = self._generate_client(node=node)
            if not client:
                continue
            await client.activate_user(username=sub.server_key, access=node.access)

    async def deactivate_subscription(self, sub: Subscription, node: Optional[Node] = None) -> None:
        for node in sub.nodes if not node else [node]:
            client = self._generate_client(node=node)
            if not client:
                continue
            await client.deactivate_user(username=sub.server_key, access=node.access)

    async def remove_subscription(self, username: str, nodes: list[Node]) -> None:
        for node in nodes:
            client = self._generate_client(node=node)
            if not client:
                continue
            await client.remove_user(username=username, access=node.access)

    async def sync_config(
        self,
        sub: Subscription,
        node: Optional[Node],
        user: Optional[MarzbanUserResponse | MarzneshinUserResponse | RustneshinUserResponse],
        configs: list[MarzbanProxyInbound | MarzneshinServiceResponce | RustneshinServiceResponse],
    ) -> None:
        data = {}
        data["username"] = sub.server_key
        data = self._generate_sync_configs(sub=sub, data=data, should=configs, current=user, node=node)
        if not data:
            return
        client = self._generate_client(node=node)
        if not client:
            return
        await client.update_user(username=user.username, data=data, access=node.access)

    async def sync_configs(
        self,
        sub: Subscription,
    ) -> None:
        for node in sub.nodes:
            client = self._generate_client(node=node)
            if not client:
                continue
            user = await client.get_user(username=sub.server_key, access=node.access)
            if not user:
                continue
            configs = get_cached_configs(node.id)
            if not configs:
                configs = await self.get_configs(node=node)
            if not configs:
                continue
            await self.sync_config(sub=sub, node=node, user=user, configs=configs)

    async def sync_subscription(self, username: str, node: Optional[Node] = None) -> None:
        async with GetDB() as db:
            sub = await Subscription.get_by_username(db, username)
            if not sub:
                return

            for node in sub.nodes if not node else [node]:
                user = await self.get_subscription(sub=sub, node=node)
                if not node.availabled:
                    if not user:
                        continue
                    if user.is_active:
                        await self.deactivate_subscription(sub=sub, node=node)
                    continue
                if not user:
                    await self.create_subscription(sub=sub, node=node)
                    continue
                if node.id not in sub.node_ids:
                    await self.remove_subscription(sub=sub, node=node)
                    continue
                if not sub.is_active and user.is_active:
                    await self.deactivate_subscription(sub=sub, node=node)
                elif sub.is_active and not user.is_active:
                    await self.activate_subscription(sub=sub, node=node)

    async def get_subscription(
        self, sub: Subscription, node: Node
    ) -> Optional[MarzbanUserResponse | MarzneshinUserResponse | RustneshinUserResponse]:
        client = self._generate_client(node=node)
        if not client:
            return None
        return await client.get_user(username=sub.server_key, access=node.access)

    async def get_all_subscriptions(
        self,
        node: Node,
        *,
        usernames: Optional[list[str]] = None,
        page: int = 1,
        size: int = 100,
        activate: Optional[bool] = None,
    ) -> list[MarzbanUserResponse | MarzneshinUserResponse | RustneshinUserResponse] | None:
        client = self._generate_client(node=node)
        if not client:
            return None
        return await client.get_users(usernames=usernames, page=page, size=size, access=node.access, activate=activate)

    async def get_subscriptions_count(self, node: Node) -> Optional[int]:
        client = self._generate_client(node=node)
        if not client:
            return None
        return await client.get_users_count(access=node.access)

    async def change_subscription(
        self,
        sub: Subscription,
        node: Optional[Node] = None,
    ):
        for node in sub.nodes if not node else [node]:
            if node.category in [NodeCategory.marzneshin, NodeCategory.rustneshin]:
                continue
            client = self._generate_client(node=node)
            if not client:
                continue
            configs = get_cached_configs(node.id)
            if not configs:
                configs = await self.get_configs(node=node)
            if not configs:
                continue
            data = {}
            data = self._generate_configs(sub=sub, data=data, configs=configs, node=node)
            await client.update_user(username=sub.server_key, data=data, access=node.access)

    async def get_scripted_users(self, node: Node) -> Optional[dict]:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0), limits=httpx.Limits(max_keepalive_connections=5)
        ) as client:
            try:
                r = await client.get(
                    f"{node.script_url}/api/users",
                    headers={"X-Api-Key": node.script_secret},
                )
                r.raise_for_status()
                return r.json()
            except httpx.RequestError as e:
                logger.error(f"HTTPX request error: {e}")
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTPX bad status: {e.response.status_code}")
            return None
