from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import (
    Column,
    String,
    Integer,
    ForeignKey,
    Table,
    select,
    func,
)
from sqlalchemy.orm import mapped_column, Mapped, relationship, joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.services import ServiceCreate, ServiceUpdate

from .node import Node
from ..core import Base

service_node_association = Table(
    "service_node_association",
    Base.metadata,
    Column("service_id", Integer, ForeignKey("services.id", ondelete="CASCADE"), primary_key=True),
    Column("node_id", Integer, ForeignKey("nodes.id"), primary_key=True),
)
service_admin_association = Table(
    "service_admin_association",
    Base.metadata,
    Column("service_id", Integer, ForeignKey("services.id", ondelete="CASCADE"), primary_key=True),
    Column("admin_id", Integer, ForeignKey("admins.id"), primary_key=True),
)
service_subscription_association = Table(
    "service_subscription_association",
    Base.metadata,
    Column("service_id", Integer, ForeignKey("services.id", ondelete="CASCADE"), primary_key=True),
    Column("subscription_id", Integer, ForeignKey("subscriptions.id"), primary_key=True),
)


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    remark: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    nodes: Mapped[List["Node"]] = relationship("Node", secondary=service_node_association, back_populates=None, lazy="joined")

    @property
    def node_ids(self) -> List[int]:
        return [node.id for node in self.nodes if not node.removed]

    @classmethod
    async def get_by_id(cls, db: AsyncSession, key: int) -> Optional["Service"]:
        result = await db.execute(select(cls).options(joinedload(cls.nodes)).where(cls.id == key))
        return result.scalars().first()

    @classmethod
    async def get_by_remark(cls, db: AsyncSession, remark: str) -> Optional["Service"]:
        result = await db.execute(select(cls).options(joinedload(cls.nodes)).where(cls.remark == remark))
        return result.scalars().first()

    @classmethod
    async def get_all(
        cls,
        db: AsyncSession,
        *,
        page: Optional[int] = None,
        size: Optional[int] = None,
    ) -> List["Service"]:
        query = select(cls).options(joinedload(cls.nodes))

        if page is not None and size is not None:
            if page < 1:
                page = 1
            query = query.offset((page - 1) * size).limit(size)

        result = await db.execute(query)
        return result.scalars().unique().all()

    @classmethod
    async def create(
        cls,
        db: AsyncSession,
        data: ServiceCreate,
    ) -> "Service":
        service = cls(remark=data.remark)
        db.add(service)
        if data.node_ids:
            result = await db.execute(select(Node).where(Node.id.in_(data.node_ids)))
            nodes = result.scalars().unique().all()
            service.nodes.extend(nodes)
        await db.flush()
        await db.refresh(service)
        return service

    @classmethod
    async def update(
        cls,
        db: AsyncSession,
        service: "Service",
        data: ServiceUpdate,
    ) -> "Service":
        if data.remark is not None:
            service.remark = data.remark
        if data.node_ids is not None:
            result = await db.execute(select(Node).where(Node.id.in_(data.node_ids)))
            nodes = result.scalars().unique().all()
            service.nodes = nodes
        await db.flush()
        await db.refresh(service)
        return service

    @classmethod
    async def remove(cls, db: AsyncSession, service: "Service") -> None:
        await db.delete(service)
        await db.flush()

    @classmethod
    async def get_services_users_count(
        cls, db: AsyncSession, service_ids: list[int], owner_id: Optional[int] = None
    ) -> dict[int, int]:
        from .subscription import Subscription

        query = (
            select(service_subscription_association.c.service_id, func.count(Subscription.id))
            .join(service_subscription_association, Subscription.id == service_subscription_association.c.subscription_id)
            .where(service_subscription_association.c.service_id.in_(service_ids))
            .where(Subscription.removed == False)
            .group_by(service_subscription_association.c.service_id)
        )
        if owner_id is not None:
            query = query.where(Subscription.owner_id == owner_id)
        result = await db.execute(query)
        return dict(result.all())
