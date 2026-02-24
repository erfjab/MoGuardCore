from enum import StrEnum
from datetime import datetime
from pydantic import BaseModel


class NodeCategory(StrEnum):
    marzban = "marzban"
    marzneshin = "marzneshin"
    rustneshin = "rustneshin"


class NodeResponse(BaseModel):
    id: int
    enabled: bool
    remark: str
    category: NodeCategory
    username: str
    password: str
    host: str
    current_usage: int
    last_used_at: datetime | None
    usage_rate: float | None
    offset_link: int
    batch_size: int
    priority: int
    script_url: str | None
    script_secret: str | None
    show_configs: bool | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NodeCreate(BaseModel):
    remark: str
    category: NodeCategory
    username: str
    password: str
    host: str
    offset_link: int = 0
    batch_size: int = 1
    priority: int = 0
    script_url: str | None = None
    script_secret: str | None = None
    usage_rate: float = 1.0
    show_configs: bool = True


class NodeUpdate(BaseModel):
    remark: str | None = None
    username: str | None = None
    password: str | None = None
    host: str | None = None
    offset_link: int | None = None
    batch_size: int | None = None
    priority: int | None = None
    usage_rate: float | None = None
    script_url: str | None = None
    script_secret: str | None = None
    show_configs: bool | None = None


class NodeStatsResponse(BaseModel):
    total_nodes: int
    active_nodes: int
    inactive_nodes: int

    class Config:
        from_attributes = True
