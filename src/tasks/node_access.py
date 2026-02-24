import time
from src.db import GetDB, Node
from src.guard_node import GuardNodeManager


async def upsert_access() -> None:
    async with GetDB() as db:
        nodes = await Node.get_all(db)
        for node in nodes:
            if node.access and node.access_updated_at and (time.time() - node.access_updated_at.timestamp()) < 8 * 60 * 60:
                continue
            node_access = await GuardNodeManager.register(
                username=node.username, password=node.password, host=node.host, category=node.category
            )
            if not node_access:
                continue
            await Node.upsert_access(db, node, node_access)
    del nodes
