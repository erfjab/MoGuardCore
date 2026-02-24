from datetime import datetime, timedelta
from typing import Dict, Optional, List, TYPE_CHECKING

from sqlalchemy import (
    String,
    Integer,
    DateTime,
    Boolean,
    Float,
    or_,
    select,
    and_,
)
from sqlalchemy.orm import mapped_column, Mapped, relationship
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.hybrid import hybrid_property
from src.models.nodes import NodeCategory, NodeUpdate, NodeCreate
from ..core import Base

if TYPE_CHECKING:
    from .subscription import SubscriptionUsage


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=True)
    removed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)

    remark: Mapped[str] = mapped_column(String(128), nullable=True, index=True)
    category: Mapped[NodeCategory] = mapped_column(String(32), nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=True)
    password: Mapped[str] = mapped_column(String(64), nullable=True)
    host: Mapped[str] = mapped_column(String(128), nullable=True)
    usage_rate: Mapped[Optional[float]] = mapped_column(Float, default=1.0, nullable=True)
    offset_link: Mapped[int] = mapped_column(Integer, default=0, nullable=True)
    batch_size: Mapped[int] = mapped_column(Integer, default=1, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=True)
    access: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    access_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(), nullable=True)
    script_secret: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    script_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    show_configs: Mapped[Optional[bool]] = mapped_column(Boolean, default=True, nullable=True)
    rate_display: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def is_scripted(self) -> bool:
        return (
            self.script_url is not None
            and self.script_url != ""
            and self.script_secret is not None
            and self.script_secret != ""
        )

    @hybrid_property
    def should_upsert_access(self) -> bool:
        if not self.access:
            return True
        if not self.access_updated_at:
            return True
        return (datetime.utcnow() - self.access_updated_at) > timedelta(hours=8)

    @should_upsert_access.expression
    def should_upsert_access(cls) -> bool:
        return or_(
            cls.access == None,  # noqa: E711
            (datetime.utcnow() - cls.access_updated_at) > timedelta(hours=8),
        )

    @hybrid_property
    def availabled(self) -> bool:
        return self.enabled and not self.removed

    @availabled.expression
    def availabled(cls) -> bool:
        return and_(cls.enabled == True, cls.removed == False)  # noqa: E712

    @property
    def last_used_at(self) -> Optional[datetime]:
        return None

    @property
    def current_usage(self) -> int:
        return 0

    @classmethod
    async def get_by_id(cls, db: AsyncSession, key: int) -> Optional["Node"]:
        result = await db.execute(
            select(cls).where(cls.id == key).where(cls.removed == False)  # noqa: E712
        )
        return result.scalars().first()

    @classmethod
    async def get_by_remark(cls, db: AsyncSession, remark: str) -> Optional["Node"]:
        result = await db.execute(
            select(cls).where(cls.remark == remark).where(cls.removed == False)  # noqa: E712
        )
        return result.scalars().first()

    @classmethod
    async def get_all(
        cls,
        db: AsyncSession,
        *,
        page: Optional[int] = None,
        size: Optional[int] = None,
        availabled: bool = None,
        should_upsert_access: bool = None,
        removed: bool = False,
    ) -> List["Node"]:
        query = select(cls).where(cls.removed == removed).order_by(cls.created_at.desc())

        if availabled is not None:
            query = query.filter(cls.availabled == availabled)
        if should_upsert_access is not None:
            query = query.filter(cls.should_upsert_access == should_upsert_access)
        if page is not None and size is not None:
            if page < 1:
                page = 1
            query = query.offset((page - 1) * size).limit(size)

        result = await db.execute(query)
        return result.scalars().unique().all()

    @classmethod
    async def get_stats(cls, db: AsyncSession) -> Dict[str, int]:
        nodes = await cls.get_all(db, removed=False)
        return {
            "total_nodes": len(nodes),
            "active_nodes": len([node for node in nodes if node.enabled]),
            "inactive_nodes": len([node for node in nodes if not node.enabled]),
        }

    @classmethod
    async def create(
        cls,
        db: AsyncSession,
        data: NodeCreate,
        access: Optional[str] = None,
    ) -> "Node":
        node = cls(
            remark=data.remark,
            category=data.category,
            username=data.username,
            password=data.password,
            host=data.host,
            offset_link=data.offset_link,
            batch_size=data.batch_size,
            priority=data.priority,
            usage_rate=data.usage_rate,
            script_url=data.script_url,
            script_secret=data.script_secret,
            show_configs=data.show_configs,
            rate_display=data.rate_display,
        )
        db.add(node)
        if access:
            node.access = access
            node.access_updated_at = datetime.utcnow()
        await db.flush()
        await db.refresh(node)
        return node

    @classmethod
    async def upsert_access(cls, db: AsyncSession, node: "Node", access: str) -> "Node":
        node.access = access
        node.access_updated_at = datetime.utcnow()
        await db.flush()
        await db.refresh(node)
        return node

    @classmethod
    async def enable(cls, db: AsyncSession, node: "Node") -> "Node":
        node.enabled = True
        await db.flush()
        await db.refresh(node)
        return node

    @classmethod
    async def disable(cls, db: AsyncSession, node: "Node") -> "Node":
        node.enabled = False
        await db.flush()
        await db.refresh(node)
        return node

    @classmethod
    async def update(
        cls,
        db: AsyncSession,
        node: "Node",
        data: NodeUpdate,
        access: Optional[str] = None,
    ) -> "Node":
        if data.remark is not None:
            node.remark = data.remark
        if data.username is not None:
            node.username = data.username
        if data.password is not None:
            node.password = data.password
        if data.host is not None:
            node.host = data.host
        if access:
            node.access = access
            node.access_updated_at = datetime.utcnow()
        if data.offset_link is not None:
            node.offset_link = data.offset_link
        if data.batch_size is not None:
            node.batch_size = data.batch_size
        if data.priority is not None:
            node.priority = data.priority
        if data.usage_rate is not None:
            node.usage_rate = data.usage_rate
        if data.script_url is not None:
            node.script_url = data.script_url
        if data.script_secret is not None:
            node.script_secret = data.script_secret
        if data.rate_display is not None:
            node.rate_display = data.rate_display
        if data.show_configs is not None:
            node.show_configs = data.show_configs
        await db.flush()
        await db.refresh(node)
        return node

    @classmethod
    async def remove(cls, db: AsyncSession, node: "Node") -> "Node":
        node.removed = True
        await db.flush()
        await db.refresh(node)
        return node
