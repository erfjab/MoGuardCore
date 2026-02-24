import asyncio
from datetime import datetime, timedelta
from secrets import token_hex
from typing import Optional, TYPE_CHECKING, List

from sqlalchemy import (
    ForeignKey,
    String,
    BigInteger,
    Integer,
    DateTime,
    Boolean,
    case,
    func,
    select,
    update,
)
from sqlalchemy.orm import mapped_column, Mapped, relationship, selectinload, joinedload, lazyload, load_only, defaultload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.hybrid import hybrid_property
from src.config import logger
from src.models.subscriptions import (
    SubscriptionCreate,
    SubscriptionStatsResponse,
    SubscriptionUpdate,
    AutoRenewalCreate,
    AutoRenewalUpdate,
)
from src.utils.format import FormatUtils
from src.utils.notif import NotificationService
from .servies import Service, service_subscription_association
from ..core import Base

if TYPE_CHECKING:
    from .admin import Admin
    from .node import Node


class SubscriptionAutoRenewal(Base):
    __tablename__ = "subscription_auto_renewals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    subscription_id: Mapped[int] = mapped_column(Integer, ForeignKey("subscriptions.id"), nullable=False, index=True)
    limit_expire: Mapped[int] = mapped_column(BigInteger, nullable=True, default=0)
    limit_usage: Mapped[int] = mapped_column(BigInteger, nullable=True, default=0)
    reset_usage: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    subscription: Mapped["Subscription"] = relationship("Subscription", back_populates="auto_renewals", lazy="joined")

    @classmethod
    async def create(
        cls,
        db: AsyncSession,
        subscription: "Subscription",
        data: "AutoRenewalCreate",
    ) -> None:
        renewal = cls(
            subscription_id=subscription.id,
            limit_expire=data.limit_expire,
            limit_usage=data.limit_usage,
            reset_usage=data.reset_usage,
        )
        db.add(renewal)

    @classmethod
    async def update(
        cls,
        renewal: "SubscriptionAutoRenewal",
        data: "AutoRenewalUpdate",
    ) -> None:
        if data.limit_expire is not None:
            renewal.limit_expire = data.limit_expire
        if data.limit_usage is not None:
            renewal.limit_usage = data.limit_usage
        if data.reset_usage is not None:
            renewal.reset_usage = data.reset_usage


class SubscriptionUsageLogs(Base):
    __tablename__ = "subscription_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    subscription_id: Mapped[int] = mapped_column(Integer, ForeignKey("subscriptions.id"), nullable=False, index=True)
    usage: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=datetime.utcnow, index=True)

    @classmethod
    async def get_all(cls, db: AsyncSession, subscription_id: Optional[int] = None) -> List["SubscriptionUsageLogs"]:
        query = select(cls)
        if subscription_id is not None:
            query = query.where(cls.subscription_id == subscription_id)
        result = await db.execute(query)
        return result.scalars().unique().all()

    @classmethod
    async def create(cls, db: AsyncSession, subscription_id: int, usage: int) -> None:
        log = SubscriptionUsageLogs(
            subscription_id=subscription_id,
            usage=usage,
            created_at=datetime.utcnow().replace(minute=0, second=0, microsecond=0),
        )
        db.add(log)
        await db.flush()
        await db.refresh(log)


class SubscriptionUsage(Base):
    __tablename__ = "subscription_usages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    subscription_id: Mapped[int] = mapped_column(Integer, ForeignKey("subscriptions.id"), nullable=False, index=True)
    node_id: Mapped[int] = mapped_column(Integer, ForeignKey("nodes.id"), nullable=False, index=True)
    usage: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    _usage: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), default=datetime.utcnow, onupdate=datetime.utcnow)

    @classmethod
    async def get_all(cls, db: AsyncSession) -> List["SubscriptionUsage"]:
        result = await db.execute((select(cls)))
        return result.scalars().unique().all()


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    username: Mapped[str] = mapped_column(String(32), nullable=True, unique=True)
    owner_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("admins.id"), nullable=True, index=True)
    access_key: Mapped[str] = mapped_column(String(32), nullable=True, index=True)
    server_key: Mapped[str] = mapped_column(String(32), nullable=True)
    telegram_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    discord_webhook_url: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=True)
    activated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=True)
    reached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    debted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    onreached_expire: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    onreached_usage: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    removed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True, index=True)
    auto_delete_days: Mapped[int] = mapped_column(Integer, default=0, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    limit_usage: Mapped[int] = mapped_column(BigInteger, nullable=True)
    reset_usage: Mapped[int] = mapped_column(BigInteger, default=0, nullable=True)
    limit_expire: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    last_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(), nullable=True)
    last_revoke_at: Mapped[Optional[datetime]] = mapped_column(DateTime(), nullable=True)
    last_request_at: Mapped[Optional[datetime]] = mapped_column(DateTime(), nullable=True)
    last_client_agent: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    inactive_at: Mapped[Optional[datetime]] = mapped_column(DateTime(), nullable=True)
    reached_at: Mapped[Optional[datetime]] = mapped_column(DateTime(), nullable=True)
    removed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), default=datetime.utcnow, onupdate=datetime.utcnow)

    total_usage: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    online_at: Mapped[Optional[datetime]] = mapped_column(DateTime(), nullable=True)

    changed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)

    owner: Mapped[Optional["Admin"]] = relationship("Admin", back_populates=None, lazy="joined")
    services: Mapped[List["Service"]] = relationship(
        "Service", secondary=service_subscription_association, back_populates=None, lazy="joined"
    )
    auto_renewals: Mapped[List["SubscriptionAutoRenewal"]] = relationship(
        "SubscriptionAutoRenewal", back_populates="subscription", lazy="joined", cascade="all, delete-orphan"
    )

    @property
    def service_ids(self) -> List[int]:
        return [service.id for service in self.services if service.id in self.owner.service_ids]

    @hybrid_property
    def agent_category(self) -> Optional[str]:
        if not self.last_client_agent:
            return None
        return self.last_client_agent.split("/")[0] if "/" in self.last_client_agent else self.last_client_agent

    @agent_category.expression
    def agent_category(cls):
        return case(
            [
                (cls.last_client_agent == None, None),
                (cls.last_client_agent.like("%/%"), func.split_part(cls.last_client_agent, "/", 1)),
            ],
            else_=cls.last_client_agent,
        )

    @property
    def format(self) -> dict:
        emoji_dict = {
            True: "✅",
            False: "❌",
        }
        return {
            "id": self.id,
            "username": self.username,
            "owner_username": self.owner_username,
            "access_key": self.access_key,
            "enabled": emoji_dict[self.enabled],
            "activated": emoji_dict[self.activated],
            "limited": emoji_dict[self.limited],
            "pending": emoji_dict[self.pending],
            "expired": emoji_dict[self.expired],
            "is_active": emoji_dict[self.is_active],
            "limit_usage": FormatUtils.byte_convert(self.limit_usage) if self.limit_usage and self.limit_usage > 0 else "♾️",
            "current_usage": FormatUtils.byte_convert(self.current_usage),
            "left_usage": FormatUtils.byte_convert(self.limit_usage - self.current_usage)
            if self.limit_usage and self.limit_usage > 0
            else "♾️",
            "expire_date": FormatUtils.date_convert(self.limit_expire) if self.limit_expire and self.limit_expire != 0 else "♾️",
            "expire_in": FormatUtils.time_convert(self.limit_expire) if self.limit_expire and self.limit_expire != 0 else "♾️",
            "expire_in_days": FormatUtils.day_convert(self.limit_expire)
            if self.limit_expire and self.limit_expire != 0
            else "♾️",
        }

    @property
    def usage_precentage(self) -> Optional[int]:
        if not self.limit_usage or self.limit_usage <= 0:
            return None
        return int((self.current_usage / self.limit_usage) * 100)

    @property
    def left_expire_days(self) -> Optional[int]:
        if not self.limit_expire or self.limit_expire <= 0:
            return None
        return max(0, (self.limit_expire - int(datetime.utcnow().timestamp())) // 86400)

    @property
    def expire_left_seconds(self) -> Optional[int]:
        if not self.limit_expire or self.limit_expire <= 0:
            return None
        return int(self.limit_expire - int(datetime.utcnow().timestamp()))

    @property
    def placeholders(self) -> list[dict]:
        if not self.owner or not self.owner.placeholders:
            return []
        places = [placeholder for placeholder in self.owner.info_placeholders]
        if self.limited:
            places.extend([placeholder for placeholder in self.owner.limited_placeholders])
        elif self.expired:
            places.extend([placeholder for placeholder in self.owner.expired_placeholders])
        elif not self.enabled:
            places.extend([placeholder for placeholder in self.owner.disabled_placeholders])
        return places

    @property
    def owner_username(self) -> str:
        return self.owner.username if self.owner else "system"

    @property
    def link(self) -> str:
        if self.owner and self.owner.access_prefix:
            if self.owner.username_tag:
                return f"{self.owner.access_prefix}/{self.owner.access_tag or 'guards'}/{self.access_key}#{self.username}"
            return f"{self.owner.access_prefix}/{self.owner.access_tag or 'guards'}/{self.access_key}"
        return f"/{self.owner.access_tag or 'guards'}/{self.access_key}"

    @property
    def nodes(self) -> List["Node"]:
        return list(
            set(
                [
                    node
                    for service in self.services
                    if service.id in self.owner.service_ids
                    for node in service.nodes
                    if not node.removed
                ]
            )
        )

    @property
    def should_be_remove(self) -> bool:
        return (self.reached_at and (datetime.utcnow() - self.reached_at) > timedelta(days=1)) or (
            self.inactive_at and (datetime.utcnow() - self.inactive_at) > timedelta(days=1)
        )

    @property
    def node_ids(self) -> List[int]:
        return [int(node.id) for node in self.nodes]

    @hybrid_property
    def is_online(self) -> bool:
        if not self.online_at:
            return False
        return (datetime.utcnow() - self.online_at) <= timedelta(seconds=120)

    @is_online.expression
    def is_online(cls):
        threshold = datetime.utcnow() - timedelta(seconds=120)
        return cls.online_at >= threshold

    @hybrid_property
    def current_usage(self) -> int:
        return self.total_usage - (self.reset_usage or 0)

    @current_usage.expression
    def current_usage(cls):
        return cls.total_usage - func.coalesce(cls.reset_usage, 0)

    @hybrid_property
    def limited(self) -> bool:
        if not self.limit_usage or self.limit_usage <= 0:
            return False
        return (self.limit_usage - self.current_usage) < 0

    @limited.expression
    def limited(cls):
        return (func.coalesce(cls.limit_usage, 0) > 0) & (
            (func.coalesce(cls.limit_usage, 0) - (cls.total_usage - func.coalesce(cls.reset_usage, 0))) < 0
        )

    @hybrid_property
    def expired(self) -> bool:
        if self.limit_expire > 0:
            now_ts = int(datetime.utcnow().timestamp())
            return now_ts > self.limit_expire
        return False

    @expired.expression
    def expired(cls):
        now_ts = int(datetime.utcnow().timestamp())
        return (cls.limit_expire > 0) & (cls.limit_expire < now_ts)

    @hybrid_property
    def pending(self) -> bool:
        return self.limit_expire < 0

    @pending.expression
    def pending(cls):
        return cls.limit_expire < 0

    @hybrid_property
    def is_active(self) -> bool:
        return self.enabled and self.activated and not self.expired and not self.limited and not self.debted

    @is_active.expression
    def is_active(cls):
        now_ts = int(datetime.utcnow().timestamp())
        return (
            (cls.enabled == True)  # noqa: E712
            & (cls.activated == True)  # noqa: E712
            & ((cls.limit_expire <= 0) | (now_ts <= cls.limit_expire))
            & ((cls.limit_usage <= 0) | ((cls.limit_usage - (cls.total_usage - func.coalesce(cls.reset_usage, 0))) >= 0))
            & (cls.debted == False)  # noqa: E712
        )

    @classmethod
    def generate_access_key(cls) -> str:
        return token_hex(16)

    @classmethod
    def generate_server_key(cls) -> str:
        return token_hex(4)

    @classmethod
    async def get_by_id(cls, db: AsyncSession, key: int) -> Optional["Subscription"]:
        result = await db.execute(
            select(cls)
            .options(
                selectinload(cls.services).selectinload(Service.nodes),
            )
            .where(cls.id == key, cls.removed == False)  # noqa: E712
        )
        return result.scalars().first()

    @classmethod
    async def get_by_username(cls, db: AsyncSession, username: str) -> Optional["Subscription"]:
        result = await db.execute(
            select(cls)
            .options(
                selectinload(cls.services).selectinload(Service.nodes),
            )
            .where(cls.username == username, cls.removed == False)  # noqa: E712
        )
        return result.scalars().first()

    @classmethod
    async def get_by_usernames(cls, db: AsyncSession, usernames: List[str]) -> List["Subscription"]:
        result = await db.execute(
            select(cls)
            .options(
                selectinload(cls.services).selectinload(Service.nodes),
            )
            .where(cls.username.in_(usernames), cls.removed == False)  # noqa: E712
        )
        return result.scalars().unique().all()

    @classmethod
    async def get_by_secret(cls, db: AsyncSession, secret: str) -> Optional["Subscription"]:
        result = await db.execute(
            select(cls)
            .options(
                selectinload(cls.services).selectinload(Service.nodes),
            )
            .where(cls.access_key == secret, cls.removed == False)  # noqa: E712
        )
        return result.scalars().first()

    @classmethod
    async def count(
        cls,
        db: AsyncSession,
        *,
        owner_id: Optional[int] = None,
        limited: Optional[bool] = None,
        expired: Optional[bool] = None,
        is_active: Optional[bool] = None,
        enabled: Optional[bool] = None,
        online: Optional[bool] = None,
        pending: Optional[bool] = None,
    ) -> int:
        query = select(func.count()).select_from(cls).where(cls.removed == False)  # noqa: E712
        if owner_id is not None:
            query = query.where(cls.owner_id == owner_id)
        if limited is not None:
            query = query.where(cls.limited == limited)
        if expired is not None:
            query = query.where(cls.expired == expired)
        if is_active is not None:
            query = query.where(cls.is_active == is_active)
        if enabled is not None:
            query = query.where(cls.enabled == enabled)
        if online is not None:
            query = query.where(cls.is_online == online)
        if pending is not None:
            query = query.where(cls.pending == pending)
        result = await db.execute(query)
        return result.scalar_one()

    @classmethod
    async def get_all(
        cls,
        db: AsyncSession,
        *,
        page: Optional[int] = None,
        size: Optional[int] = None,
        is_active: Optional[bool] = None,
        limited: Optional[bool] = None,
        expired: Optional[bool] = None,
        enabled: Optional[bool] = None,
        search: Optional[str] = None,
        online: Optional[bool] = None,
        order_by: Optional[str] = None,
        reached: Optional[bool] = None,
        total_usage: Optional[int] = None,
        sub_id: Optional[int] = None,
        owner_id: Optional[int] = None,
        removed: bool = False,
        pending: Optional[bool] = None,
        load_service_nodes: bool = False,
        load_services: bool = False,
    ) -> List["Subscription"]:
        query = select(cls)
        if load_service_nodes:
            from .admin import Admin

            query = query.options(
                selectinload(cls.services).selectinload(Service.nodes),
                joinedload(cls.owner).selectinload(Admin.services),
            )
        elif load_services:
            query = query.options(selectinload(cls.services))
        if removed is not None:
            query = query.where(cls.removed == removed)
        if search:
            query = query.where(cls.username.ilike(f"%{search}%"))
        if online is not None:
            query = query.where(cls.is_online == online)
        if enabled is not None:
            query = query.where(cls.enabled == enabled)
        if is_active is not None:
            query = query.where(cls.is_active == is_active)
        if sub_id is not None:
            query = query.where(cls.id == sub_id)
        if limited is not None:
            query = query.where(cls.limited == limited)
        if expired is not None:
            query = query.where(cls.expired == expired)
        if reached is not None:
            query = query.where(cls.reached == reached)
        if total_usage is not None:
            query = query.where(cls.total_usage == total_usage)
        if owner_id is not None:
            query = query.where(cls.owner_id == owner_id)
        if pending is not None:
            query = query.where(cls.pending == pending)
        if order_by is not None:
            if order_by == "username_asc":
                query = query.order_by(cls.username.asc())
            elif order_by == "username_desc":
                query = query.order_by(cls.username.desc())
            elif order_by == "created_at_asc":
                query = query.order_by(cls.created_at.asc())
            elif order_by == "created_at_desc":
                query = query.order_by(cls.created_at.desc())
            elif order_by == "updated_at_asc":
                query = query.order_by(cls.updated_at.asc())
            elif order_by == "updated_at_desc":
                query = query.order_by(cls.updated_at.desc())
            elif order_by == "current_usage_asc":
                query = query.order_by(cls.current_usage.asc())
            elif order_by == "current_usage_desc":
                query = query.order_by(cls.current_usage.desc())
            elif order_by == "expire_date_asc":
                query = query.order_by(cls.limit_expire.asc())
            elif order_by == "expire_date_desc":
                query = query.order_by(cls.limit_expire.desc())
            elif order_by == "online_at_asc":
                query = query.order_by(cls.online_at.asc().nulls_last())
            elif order_by == "online_at_desc":
                query = query.order_by(cls.online_at.desc().nulls_first())
            elif order_by == "last_request_at_asc":
                query = query.order_by(cls.last_request_at.asc().nulls_last())
            elif order_by == "last_request_at_desc":
                query = query.order_by(cls.last_request_at.desc().nulls_first())
            elif order_by == "last_revoke_at_asc":
                query = query.order_by(cls.last_revoke_at.asc().nulls_last())
            elif order_by == "last_revoke_at_desc":
                query = query.order_by(cls.last_revoke_at.desc().nulls_first())
            elif order_by == "last_reset_at_asc":
                query = query.order_by(cls.last_reset_at.asc().nulls_last())
            elif order_by == "last_reset_at_desc":
                query = query.order_by(cls.last_reset_at.desc().nulls_first())
            elif order_by == "left_usage_asc":
                query = query.order_by((cls.limit_usage - (cls.total_usage - func.coalesce(cls.reset_usage, 0))).asc())
            elif order_by == "left_usage_desc":
                query = query.order_by((cls.limit_usage - (cls.total_usage - func.coalesce(cls.reset_usage, 0))).desc())
            elif order_by == "limit_usage_asc":
                query = query.order_by(cls.limit_usage.asc())
            elif order_by == "limit_usage_desc":
                query = query.order_by(cls.limit_usage.desc())

        if page is not None and size is not None:
            if page < 1:
                page = 1
            query = query.offset((page - 1) * size).limit(size)

        result = await db.execute(query)
        return result.scalars().unique().all()

    @classmethod
    async def get_all_for_reached_tracker(cls, db: AsyncSession) -> List["Subscription"]:
        from .admin import Admin

        query = (
            select(cls)
            .options(
                lazyload("*"),
                load_only(
                    cls.id,
                    cls.username,
                    cls.owner_id,
                    cls.telegram_id,
                    cls.discord_webhook_url,
                    cls.reached,
                    cls.debted,
                    cls.onreached_expire,
                    cls.onreached_usage,
                    cls.auto_delete_days,
                    cls.limit_usage,
                    cls.reset_usage,
                    cls.limit_expire,
                    cls.total_usage,
                    cls.reached_at,
                    cls.enabled,
                    cls.activated,
                    cls.removed,
                ),
                joinedload(cls.owner).load_only(
                    Admin.id,
                    Admin.expire_warning_days,
                    Admin.usage_warning_percent,
                    Admin.telegram_status,
                    Admin.telegram_token,
                    Admin.telegram_id,
                    Admin.telegram_logger_id,
                    Admin.telegram_topic_id,
                    Admin.telegram_send_subscriptions,
                    Admin.discord_webhook_status,
                    Admin.discord_webhook_url,
                    Admin.discord_send_subscriptions,
                    Admin.current_count,
                ),
                defaultload(cls.owner).lazyload("*"),
                selectinload(cls.auto_renewals).load_only(
                    SubscriptionAutoRenewal.id,
                    SubscriptionAutoRenewal.subscription_id,
                    SubscriptionAutoRenewal.limit_expire,
                    SubscriptionAutoRenewal.limit_usage,
                    SubscriptionAutoRenewal.reset_usage,
                ),
            )
            .where(cls.removed == False)  # noqa: E712
        )
        result = await db.execute(query)
        return result.scalars().unique().all()

    @classmethod
    async def create(
        cls,
        db: AsyncSession,
        data: SubscriptionCreate,
        owner: "Admin",
    ) -> "Subscription":
        subscription = cls(
            username=data.username,
            access_key=cls.generate_access_key(),
            server_key=cls.generate_server_key(),
            telegram_id=data.telegram_id,
            discord_webhook_url=data.discord_webhook_url,
            limit_usage=data.limit_usage,
            limit_expire=data.limit_expire,
            owner_id=owner.id,
            note=data.note,
            auto_delete_days=data.auto_delete_days,
        )
        owner.current_count += 1
        db.add(subscription)
        if data.service_ids:
            result = await db.execute(
                select(Service).where(Service.id.in_(data.service_ids)).where(Service.id.in_(owner.service_ids))
            )
            services = result.scalars().unique().all()
            subscription.services.extend(services)
        await db.flush()
        if data.auto_renewals:
            for renewal_data in data.auto_renewals:
                await SubscriptionAutoRenewal.create(db, subscription, renewal_data)
        await db.refresh(subscription)
        return subscription

    @classmethod
    async def update(
        cls,
        db: AsyncSession,
        subscription: "Subscription",
        data: SubscriptionUpdate,
    ) -> "Subscription":
        if data.limit_usage is not None:
            subscription.limit_usage = data.limit_usage
        if data.limit_expire is not None:
            subscription.limit_expire = data.limit_expire
        if data.username is not None:
            subscription.username = data.username
        if data.note is not None:
            subscription.note = data.note
        if data.telegram_id is not None:
            subscription.telegram_id = data.telegram_id
        if data.discord_webhook_url is not None:
            subscription.discord_webhook_url = data.discord_webhook_url
        if data.auto_delete_days is not None:
            subscription.auto_delete_days = data.auto_delete_days
        if data.service_ids is not None:
            result = await db.execute(
                select(Service).where(Service.id.in_(data.service_ids)).where(Service.id.in_(subscription.owner.service_ids))
            )
            services = result.scalars().unique().all()
            subscription.services = services
        if data.auto_renewals is not None:
            renewal_ids_to_keep = {
                renewal_data.id
                for renewal_data in data.auto_renewals
                if hasattr(renewal_data, "id") and renewal_data.id is not None
            }
            renewals_to_delete = [r for r in subscription.auto_renewals if r.id not in renewal_ids_to_keep]
            for renewal in renewals_to_delete:
                await db.delete(renewal)
            for renewal_data in data.auto_renewals:
                renewal = next((r for r in subscription.auto_renewals if r.id == renewal_data.id), None)
                if renewal:
                    await SubscriptionAutoRenewal.update(renewal, renewal_data)
                else:
                    await SubscriptionAutoRenewal.create(db, subscription, renewal_data)
        await db.flush()
        await db.refresh(subscription)
        return subscription

    @classmethod
    async def reset_usages(cls, db: AsyncSession, subscription: "Subscription") -> "Subscription":
        subscription.reset_usage = subscription.total_usage
        subscription.last_reset_at = datetime.utcnow()
        await db.flush()
        await db.refresh(subscription)
        return subscription

    @classmethod
    async def bulk_reset_usages(cls, db: AsyncSession, subscriptions: List["Subscription"]) -> List["Subscription"]:
        now = datetime.utcnow()
        ids = [s.id for s in subscriptions]
        await db.execute(update(cls).where(cls.id.in_(ids)).values(reset_usage=cls.total_usage, last_reset_at=now))
        await db.flush()
        for sub in subscriptions:
            await db.refresh(sub)
        return subscriptions

    @classmethod
    async def revoke(cls, db: AsyncSession, subscription: "Subscription") -> "Subscription":
        subscription.access_key = cls.generate_access_key()
        subscription.last_revoke_at = datetime.utcnow()
        await db.flush()
        await db.refresh(subscription)
        return subscription

    @classmethod
    async def bulk_revoke(cls, db: AsyncSession, subscriptions: List["Subscription"]) -> List["Subscription"]:
        now = datetime.utcnow()
        for sub in subscriptions:
            sub.access_key = cls.generate_access_key()
            sub.last_revoke_at = now
        await db.flush()
        for sub in subscriptions:
            await db.refresh(sub)
        return subscriptions

    @classmethod
    async def remove(cls, db: AsyncSession, subscription: "Subscription") -> "Subscription":
        subscription.removed = True
        subscription.username = None
        subscription.removed_at = datetime.utcnow()
        if subscription.owner:
            subscription.owner.current_count -= 1
        await db.flush()
        await db.refresh(subscription)
        return subscription

    @classmethod
    async def bulk_remove(cls, db: AsyncSession, subscriptions: List["Subscription"]) -> List["Subscription"]:
        now = datetime.utcnow()
        ids = [s.id for s in subscriptions]
        await db.execute(update(cls).where(cls.id.in_(ids)).values(removed=True, username=None, removed_at=now))
        await db.flush()
        for sub in subscriptions:
            await db.refresh(sub)
        return subscriptions

    @classmethod
    async def enable(cls, db: AsyncSession, subscription: "Subscription") -> "Subscription":
        subscription.enabled = True
        subscription.inactive_at = None
        await db.flush()
        await db.refresh(subscription)
        return subscription

    @classmethod
    async def bulk_enable(cls, db: AsyncSession, subscriptions: List["Subscription"]) -> List["Subscription"]:
        ids = [s.id for s in subscriptions]
        await db.execute(update(cls).where(cls.id.in_(ids)).values(enabled=True, inactive_at=None))
        await db.flush()
        for sub in subscriptions:
            await db.refresh(sub)
        return subscriptions

    @classmethod
    async def disable(cls, db: AsyncSession, subscription: "Subscription") -> "Subscription":
        subscription.enabled = False
        subscription.inactive_at = datetime.utcnow()
        await db.flush()
        await db.refresh(subscription)
        return subscription

    @classmethod
    async def bulk_disable(cls, db: AsyncSession, subscriptions: List["Subscription"]) -> List["Subscription"]:
        now = datetime.utcnow()
        ids = [s.id for s in subscriptions]
        await db.execute(update(cls).where(cls.id.in_(ids)).values(enabled=False, inactive_at=now))
        await db.flush()
        for sub in subscriptions:
            await db.refresh(sub)
        return subscriptions

    @classmethod
    async def activate(cls, db: AsyncSession, subscription: "Subscription") -> "Subscription":
        subscription.activated = True
        await db.flush()
        await db.refresh(subscription)
        return subscription

    @classmethod
    async def deactivate(cls, db: AsyncSession, subscription: "Subscription") -> "Subscription":
        subscription.activated = False
        await db.flush()
        await db.refresh(subscription)
        return subscription

    @classmethod
    async def set_last_request(
        cls,
        db: AsyncSession,
        subscription: "Subscription",
        *,
        client_agent: Optional[str] = None,
    ) -> "Subscription":
        if not subscription.last_request_at:
            await NotificationService.first_requested_subscription(subscription, client_agent=client_agent)
        subscription.last_request_at = datetime.utcnow()
        if client_agent:
            subscription.last_client_agent = client_agent[:256]
        await db.flush()
        await db.refresh(subscription)
        return subscription

    @classmethod
    async def check_exists(cls, db: AsyncSession, username: str) -> bool:
        result = await db.execute(
            select(cls).where(cls.username == username).where(cls.removed == False)  # noqa: E712
        )
        return result.scalars().first() is not None

    @classmethod
    async def bulk_check_exists(
        cls,
        db: AsyncSession,
        usernames: List[str],
        owner: Optional["Admin"] = None,
    ) -> List[str]:
        query = (
            select(cls.username).where(cls.username.in_(usernames)).where(cls.removed == False)  # noqa: E712
        )
        if owner is not None:
            query = query.where(cls.owner_id == owner.id)
        result = await db.execute(query)
        return result.scalars().all()

    @classmethod
    async def bulk_create(
        cls,
        db: AsyncSession,
        data: List[SubscriptionCreate],
        owner: "Admin",
    ) -> List["Subscription"]:
        if not data:
            return []

        owner.current_count += len(data)
        owner_service_ids = set(owner.service_ids or [])
        requested_service_ids = {
            service_id for item in data for service_id in (item.service_ids or []) if service_id in owner_service_ids
        }

        services_map: dict[int, Service] = {}
        if requested_service_ids:
            result = await db.execute(select(Service).where(Service.id.in_(requested_service_ids)))
            services_map = {service.id: service for service in result.scalars().unique().all()}

        created: list[tuple["Subscription", SubscriptionCreate]] = []
        for item in data:
            subscription = cls(
                username=item.username,
                access_key=item.access_key or cls.generate_access_key(),
                server_key=cls.generate_server_key(),
                telegram_id=item.telegram_id,
                limit_usage=item.limit_usage,
                limit_expire=item.limit_expire,
                discord_webhook_url=item.discord_webhook_url,
                owner_id=owner.id,
                note=item.note,
                auto_delete_days=item.auto_delete_days,
            )
            if item.service_ids:
                for service_id in item.service_ids:
                    service = services_map.get(service_id)
                    if service:
                        subscription.services.append(service)
            db.add(subscription)
            created.append((subscription, item))

        await db.flush()

        has_auto = False
        for subscription, item in created:
            if item.auto_renewals:
                has_auto = True
                for renewal_data in item.auto_renewals:
                    await SubscriptionAutoRenewal.create(db, subscription, renewal_data)
        if has_auto:
            await db.flush()

        ids = [subscription.id for subscription, _ in created]
        order_map = {sub_id: index for index, sub_id in enumerate(ids)}

        result = await db.execute(
            select(cls)
            .options(selectinload(cls.services).selectinload(Service.nodes))
            .options(selectinload(cls.auto_renewals))
            .where(cls.id.in_(ids))
        )
        subscriptions = result.scalars().unique().all()
        subscriptions.sort(key=lambda sub: order_map.get(sub.id, 0))
        return subscriptions

    @classmethod
    async def bulk_remove_by_admin(
        cls,
        db: AsyncSession,
        admin: "Admin",
        usernames: Optional[List[str]] = None,
        inactive: Optional[int] = None,
    ) -> None:
        now = datetime.utcnow()
        stmt = update(cls).where(cls.owner_id == admin.id)
        if usernames is not None:
            stmt = stmt.where(cls.username.in_(usernames))
        if inactive is not None:
            stmt = stmt.where(
                cls.inactive_at != None,  # noqa: E711
                cls.inactive_at <= now - timedelta(days=inactive),
            )
        stmt = stmt.values(username=None, removed=True, removed_at=now)
        await db.execute(stmt)
        await db.flush()

    @classmethod
    async def bulk_enable_by_admin(cls, db: AsyncSession, admin: "Admin") -> None:
        await db.execute(update(cls).where(cls.owner_id == admin.id).values(enabled=True, inactive_at=None))
        await db.flush()

    @classmethod
    async def bulk_disable_by_admin(cls, db: AsyncSession, admin: "Admin") -> None:
        await db.execute(update(cls).where(cls.owner_id == admin.id).values(enabled=False, inactive_at=datetime.utcnow()))
        await db.flush()

    @classmethod
    async def get_stats(cls, db: AsyncSession, owner_id: Optional[int] = None) -> "SubscriptionStatsResponse":
        stmt = select(
            func.count(cls.id).label("total"),
            func.sum(case((cls.is_active == True, 1), else_=0)).label("active"),  # noqa: E712
            func.sum(case((cls.enabled == False, 1), else_=0)).label("disabled"),  # noqa: E712
            func.sum(case((cls.expired == True, 1), else_=0)).label("expired"),  # noqa: E712
            func.sum(case((cls.limited == True, 1), else_=0)).label("limited"),  # noqa: E712
            func.sum(case((cls.last_revoke_at != None, 1), else_=0)).label("has_revoked"),  # noqa: E711
            func.sum(case((cls.last_reset_at != None, 1), else_=0)).label("has_reseted"),  # noqa: E711
            func.sum(case((cls.removed == True, 1), else_=0)).label("total_removed"),  # noqa: E712
            func.coalesce(func.sum(cls.total_usage), 0).label("total_usage"),
        )
        if owner_id is not None:
            stmt = stmt.where(cls.owner_id == owner_id)

        result = await db.execute(stmt)
        row = result.one()

        total = row.total or 0
        active = row.active or 0
        disabled = row.disabled or 0
        expired = row.expired or 0
        limited = row.limited or 0
        has_revoked = row.has_revoked or 0
        has_reseted = row.has_reseted or 0
        total_removed = row.total_removed or 0
        total_usage = row.total_usage or 0

        return SubscriptionStatsResponse(
            total=total,
            active=active,
            inactive=max(total - active, 0),
            disabled=disabled,
            expired=expired,
            limited=limited,
            has_revoked=has_revoked,
            has_reseted=has_reseted,
            total_removed=total_removed,
            total_usage=total_usage,
        )

    @classmethod
    async def bulk_upsert_usages(
        cls,
        db: AsyncSession,
        sub: "Subscription",
        usages: dict["Node", tuple[int, datetime]],
        sub_usages: List["SubscriptionUsage"],
    ) -> None:
        changed = False
        for node, (usage_value, created_at) in usages.items():
            if usage_value <= 0:
                continue

            rate = node.usage_rate or 1.0
            found = False

            for record in sub_usages:
                if record.node_id == node.id and record.created_at == created_at:
                    found = True
                    if record._usage != usage_value:
                        delta = usage_value - record._usage
                        if delta < 0:
                            logger.warning(
                                f"Usage counter decreased (treating as reset) | sub='{sub.username}' node='{node.remark}' created_at='{created_at}' old={record._usage} new={usage_value}"
                            )
                        else:
                            record.usage += int(delta * rate)
                            if record.usage < 0:
                                record.usage = 0
                            record._usage = usage_value
                            record.updated_at = datetime.utcnow()
                            changed = True
                    break

            if not found:
                new_record = SubscriptionUsage(
                    subscription_id=sub.id,
                    node_id=node.id,
                    usage=int(usage_value * rate),
                    _usage=usage_value,
                    created_at=created_at,
                )
                db.add(new_record)
                changed = True

        if changed:
            await cls.activate_expire(db, sub)

    @classmethod
    async def upsert_usage(cls, db: AsyncSession, sub: "Subscription", node: "Node", usage: int, created_at: datetime) -> None:
        if usage <= 0:
            return
        existing = await db.execute(
            select(SubscriptionUsage)
            .where(SubscriptionUsage.subscription_id == sub.id)
            .where(SubscriptionUsage.node_id == node.id)
            .where(SubscriptionUsage.created_at == created_at)
        )
        existing = existing.scalars().first()
        if existing:
            if existing._usage == usage:
                return
            delta = usage - existing._usage
            if delta < 0:
                logger.warning(
                    f"Usage counter decreased (treating as reset) | sub='{sub.username}' node='{node.remark}' created_at='{created_at}' old={existing._usage} new={usage}"
                )
                existing._usage = usage
                existing.updated_at = datetime.utcnow()
            else:
                existing.usage += int(delta * (node.usage_rate or 1.0))
                if existing.usage < 0:
                    existing.usage = 0
                existing._usage = usage
                existing.updated_at = datetime.utcnow()
        else:
            existing = SubscriptionUsage(
                subscription_id=sub.id,
                node_id=node.id,
                usage=int(usage * (node.usage_rate or 1.0)),
                _usage=usage,
                created_at=created_at,
            )
            db.add(existing)
        await cls.activate_expire(db, sub)

    @classmethod
    async def activate_expire(cls, db: AsyncSession, sub: "Subscription") -> None:
        if sub.limit_expire and sub.limit_expire < 0:
            sub.limit_expire = datetime.utcnow().timestamp() + abs(sub.limit_expire)
            logger.info(f"Activated expire for subscription '{sub.username}'")
            asyncio.create_task(NotificationService.activated_expire_subscription(sub))

    @classmethod
    async def sync_cached_usages(cls, db: AsyncSession) -> None:
        await db.execute(
            update(cls).values(
                total_usage=(
                    select(func.coalesce(func.sum(func.greatest(SubscriptionUsage.usage, 0)), 0))
                    .where(SubscriptionUsage.subscription_id == cls.id)
                    .correlate(cls)
                    .scalar_subquery()
                ),
                online_at=(
                    select(func.max(SubscriptionUsage.updated_at))
                    .where(SubscriptionUsage.subscription_id == cls.id)
                    .correlate(cls)
                    .scalar_subquery()
                ),
            )
        )
        await db.flush()

    @classmethod
    async def bulk_debted(
        cls, db: AsyncSession, *, admin: Optional["Admin"] = None, owner_ids: list[int] = None, offset: Optional[int] = None
    ) -> None:
        select_stmt = select(cls.id).where(cls.debted == True)  # noqa

        if admin is not None:
            select_stmt = select_stmt.where(cls.owner_id == admin.id)
        if owner_ids is not None:
            select_stmt = select_stmt.where(cls.owner_id.in_(owner_ids))
        if offset is not None:
            select_stmt = select_stmt.offset(offset)

        stmt = update(cls).where(cls.id.in_(select_stmt)).values(debted=True)
        await db.execute(stmt)
        await db.flush()

    @classmethod
    async def bulk_dedebted(
        cls, db: AsyncSession, *, admin: Optional["Admin"] = None, owner_ids: list[int] = None, offset: Optional[int] = None
    ) -> None:
        select_stmt = select(cls.id).where(cls.debted == True)  # noqa

        if admin is not None:
            select_stmt = select_stmt.where(cls.owner_id == admin.id)
        if owner_ids is not None:
            select_stmt = select_stmt.where(cls.owner_id.in_(owner_ids))
        if offset is not None:
            select_stmt = select_stmt.offset(offset)

        stmt = update(cls).where(cls.id.in_(select_stmt)).values(debted=False)
        await db.execute(stmt)
        await db.flush()

    @classmethod
    async def bulk_activate(
        cls, db: AsyncSession, *, admin: Optional["Admin"] = None, owner_ids: list[int] = None, offset: Optional[int] = None
    ) -> None:
        select_stmt = select(cls.id).where(cls.activated == False)  # noqa

        if admin is not None:
            select_stmt = select_stmt.where(cls.owner_id == admin.id)
        if owner_ids is not None:
            select_stmt = select_stmt.where(cls.owner_id.in_(owner_ids))
        if offset is not None:
            select_stmt = select_stmt.offset(offset)

        stmt = update(cls).where(cls.id.in_(select_stmt)).values(activated=True)
        await db.execute(stmt)
        await db.flush()

    @classmethod
    async def bulk_deactivate(
        cls, db: AsyncSession, *, admin: Optional["Admin"] = None, owner_ids: list[int] = None, offset: Optional[int] = None
    ) -> None:
        select_stmt = select(cls.id).where(cls.activated == True)  # noqa

        if admin is not None:
            select_stmt = select_stmt.where(cls.owner_id == admin.id)
        if owner_ids is not None:
            select_stmt = select_stmt.where(cls.owner_id.in_(owner_ids))
        if offset is not None:
            select_stmt = select_stmt.offset(offset)

        stmt = update(cls).where(cls.id.in_(select_stmt)).values(activated=False)
        await db.execute(stmt)
        await db.flush()

    @classmethod
    async def bulk_add_service(
        cls,
        db: AsyncSession,
        admin: "Admin",
        service: "Service",
    ) -> None:
        """Add a service to all subscriptions owned by an admin."""
        # Get all subscriptions for this admin
        query = select(cls).options(selectinload(cls.services)).where(cls.removed == False)  # noqa: E712
        if not admin.is_owner:
            query = query.where(cls.owner_id == admin.id)

        result = await db.execute(query)
        subscriptions = result.scalars().unique().all()

        # Add service to each subscription
        for subscription in subscriptions:
            if service.id not in [s.id for s in subscription.services]:
                subscription.services.append(service)

        await db.flush()

    @classmethod
    async def bulk_remove_service(
        cls,
        db: AsyncSession,
        admin: "Admin",
        service: "Service",
    ) -> None:
        """Remove a service from all subscriptions owned by an admin."""
        # Get all subscriptions for this admin
        query = select(cls).options(selectinload(cls.services)).where(cls.removed == False)  # noqa: E712
        if not admin.is_owner:
            query = query.where(cls.owner_id == admin.id)

        result = await db.execute(query)
        subscriptions = result.scalars().unique().all()

        # Remove service from each subscription
        for subscription in subscriptions:
            subscription.services = [s for s in subscription.services if s.id != service.id]

        await db.flush()

    @classmethod
    async def mark_changed(
        cls,
        db: AsyncSession,
        sub_id: int,
    ) -> Optional["Subscription"]:
        # Merge the subscription into this session if it's not attached
        subscription = await db.get(cls, sub_id)
        if not subscription:
            return None
        subscription.changed = True
        await db.flush()
        await db.refresh(subscription)
        return subscription
