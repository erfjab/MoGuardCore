"""
Cache for node configs.
Configs are fetched on startup and updated every minute.
"""

from typing import Optional
from src.guard_node.clients.marzban import MarzbanProxyInbound
from src.guard_node.clients.marzneshin import MarzneshinServiceResponce
from src.guard_node.clients.rustneshin import RustneshinServiceResponse

ConfigType = list[MarzbanProxyInbound | MarzneshinServiceResponce | RustneshinServiceResponse]


CONFIGS: dict[int, ConfigType] = {}


def get_configs(node_id: int) -> Optional[ConfigType]:
    """Get cached configs for a node"""
    return CONFIGS.get(node_id)


def set_configs(node_id: int, configs: ConfigType) -> None:
    """Set cached configs for a node"""
    CONFIGS[node_id] = configs


def clear_configs(node_id: int) -> None:
    """Clear cached configs for a node"""
    if node_id in CONFIGS:
        del CONFIGS[node_id]
