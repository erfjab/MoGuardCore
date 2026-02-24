from src.guard_node import GuardNodeManager
from src.db import GetDB, Node
from src.utils.configs import set_configs
from src.config import logger


async def update_configs_task() -> bool:
    any_failed = False
    async with GetDB() as db:
        nodes = await Node.get_all(db)
        for node in nodes:
            try:
                configs = await GuardNodeManager.get_configs(node=node)
                if configs:
                    set_configs(node.id, configs)
                    logger.debug(f"Updated configs cache for node '{node.remark}' (ID: {node.id})")
                else:
                    set_configs(node.id, [])
                    logger.warning(f"No configs found for node '{node.remark}' (ID: {node.id})")
                    any_failed = True
            except Exception as e:
                logger.error(f"Failed to update configs for node '{node.remark}' (ID: {node.id}): {e}")
                set_configs(node.id, [])
                any_failed = True
    return any_failed
