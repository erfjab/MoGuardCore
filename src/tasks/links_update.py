import base64
from src.config import logger
from src.guard_node import GuardNodeManager
from src.db import GetDB, Node, NodeCategory, Subscription
from src.utils.cache import LINKS
from src.utils.configs import get_configs


async def fetch_links_from_subscription_url(node: Node, subscription_url: str) -> list[str]:
    links = []
    try:
        url = f"{subscription_url}/v2ray" if subscription_url.startswith("http") else f"{node.host}{subscription_url}/v2ray"
        async with GuardNodeManager.session.get(url, timeout=5) as resp:
            if resp.status != 200:
                return []
            content = await resp.text()
        if not content:
            return []
        try:
            content = base64.b64decode(content).decode("utf-8")
        finally:
            links.extend(link.strip() for link in content.splitlines() if link.strip())
    except Exception as e:
        return []
    return links


async def update_links_task() -> bool:
    total = 0
    async with GetDB() as db:
        nodes = await Node.get_all(db)
        for node in nodes:
            client = GuardNodeManager._generate_client(node)
            if not client:
                if node.id not in LINKS:
                    LINKS[node.id] = []
                continue
            configs = get_configs(node.id)
            if not configs:
                if node.id not in LINKS:
                    LINKS[node.id] = []
                continue

            user = await client.get_user(username="guard", access=node.access)
            if not user:
                logger.info(f"Creating 'guard' user on node '{node.remark}' (ID: {node.id})")
                data = GuardNodeManager._generate_expire(node=node)
                data["username"] = "guard"
                data["data_limit"] = 0
                data = GuardNodeManager._generate_guard_configs(data=data, configs=configs, node=node)
                if node.category in [NodeCategory.marzneshin, NodeCategory.rustneshin]:
                    data["key"] = Subscription.generate_access_key()

                user = await client.create_user(data=data, access=node.access)
                if not user:
                    logger.error(f"Failed to create 'guard' user on node '{node.remark}' (ID: {node.id})")
                    if node.id not in LINKS:
                        LINKS[node.id] = []
                    continue

            data = {}
            data["username"] = "guard"
            data = GuardNodeManager._generate_guard_configs(data=data, configs=configs, node=node, user=user)
            if data:
                logger.info(f"Updating 'guard' user on node '{node.remark}' (ID: {node.id})")
                await client.update_user(username="guard", data=data, access=node.access)

            if node.category == NodeCategory.marzban:
                LINKS[node.id] = [link.strip() for link in user.links if link.strip()]
            elif node.category in [NodeCategory.marzneshin, NodeCategory.rustneshin]:
                LINKS[node.id] = await fetch_links_from_subscription_url(node=node, subscription_url=user.subscription_url)
            else:
                if node.id not in LINKS:
                    LINKS[node.id] = []
                continue
            total += 1
    return total != len(nodes)
