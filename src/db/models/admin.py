import base64
import hashlib
import os
from datetime import datetime
from secrets import token_hex
from typing import Optional, List

from sqlalchemy import (
    String,
    BigInteger,
    Integer,
    DateTime,
    Boolean,
    JSON,
    select,
    and_,
    update,
)
from sqlalchemy.orm import mapped_column, Mapped, relationship
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.hybrid import hybrid_property
from src.models.admins import AdminRole, AdminCreate, AdminUpdate, AdminCurrentUpdate
from .servies import service_admin_association, Service
from ..core import Base, GetDB


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=True)
    removed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    removed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(), nullable=True)

    username: Mapped[str] = mapped_column(String(64), nullable=True, unique=True)
    password: Mapped[str] = mapped_column(String(64), nullable=True)
    role: Mapped[AdminRole] = mapped_column(String(32), nullable=True)

    api_key: Mapped[str] = mapped_column(String(64), nullable=True)
    secret: Mapped[str] = mapped_column(String(32), nullable=True)

    create_access: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    update_access: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    remove_access: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)

    count_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    usage_limit: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    access_prefix: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    telegram_status: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    telegram_token: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    telegram_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    telegram_logger_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    telegram_topic_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    telegram_send_subscriptions: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)

    discord_webhook_status: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    discord_webhook_url: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    discord_send_subscriptions: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)

    expire_warning_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    usage_warning_percent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    placeholders: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    max_links: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shuffle_links: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    config_rename: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    access_title: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    access_description: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    access_tag: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    username_tag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    support_url: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    update_interval: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    announce: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    announce_url: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    totp_secret: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    totp_secret_pending: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    totp_status: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    last_totp_revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(), nullable=True)

    current_usage: Mapped[Optional[int]] = mapped_column(BigInteger, default=0, nullable=True)
    current_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    last_password_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(), nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(), nullable=True)
    last_online_at: Mapped[Optional[datetime]] = mapped_column(DateTime(), nullable=True)
    last_backup_at: Mapped[Optional[datetime]] = mapped_column(DateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), default=datetime.utcnow, onupdate=datetime.utcnow)

    services: Mapped[List["Service"]] = relationship(
        "Service",
        secondary=service_admin_association,
        back_populates=None,
        lazy="joined",
    )

    @property
    def telegram_chat_id(self) -> Optional[str]:
        return self.telegram_logger_id or self.telegram_id

    # TODO: Optimize these properties
    @property
    def info_placeholders(self) -> list[dict]:
        if not self.placeholders:
            return []
        return [p for p in self.placeholders if "info" in p.get("categories", [])]

    @property
    def limited_placeholders(self) -> list[dict]:
        if not self.placeholders:
            return []
        return [p for p in self.placeholders if "limited" in p.get("categories", [])]

    @property
    def expired_placeholders(self) -> list[dict]:
        if not self.placeholders:
            return []
        return [p for p in self.placeholders if "expired" in p.get("categories", [])]

    @property
    def disabled_placeholders(self) -> list[dict]:
        if not self.placeholders:
            return []
        return [p for p in self.placeholders if "disabled" in p.get("categories", [])]

    @property
    def left_usage(self) -> Optional[int]:
        if self.usage_limit is None or self.usage_limit == 0:
            return None
        return self.usage_limit - self.current_usage

    @property
    def reached_usage_limit(self) -> bool:
        return True if self.left_usage and self.left_usage <= 0 else False

    @property
    def left_count(self) -> Optional[int]:
        if self.count_limit is None or self.count_limit == 0:
            return None
        return self.count_limit - self.current_count

    @property
    def reached_count_limit(self) -> bool:
        return True if self.left_count and self.left_count <= 0 else False

    @property
    def is_owner(self) -> bool:
        return self.role == AdminRole.OWNER

    @property
    def service_ids(self) -> List[int]:
        return [service.id for service in self.services]

    @hybrid_property
    def availabled(self) -> bool:
        return self.enabled and not self.removed and not self.reached_usage_limit

    @availabled.expression
    def availabled(cls) -> bool:
        return and_(cls.enabled == True, cls.removed == False, cls.reached_usage_limit == False)  # noqa: E712

    def hashed_secret(self) -> str:
        return Admin.generate_hash(self.secret)

    @classmethod
    def generate_hash(cls, password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    @classmethod
    def generate_secret(cls) -> str:
        return token_hex(16)

    @classmethod
    def generate_api_key(cls) -> str:
        return token_hex(32)

    @classmethod
    async def get_by_id(cls, db: AsyncSession, key: int) -> Optional["Admin"]:
        result = await db.execute(
            select(cls).where(cls.id == key).where(cls.removed == False)  # noqa: E712
        )
        return result.scalars().first()

    @classmethod
    async def get_by_username(cls, db: AsyncSession, username: str) -> Optional["Admin"]:
        result = await db.execute(
            select(cls).where(cls.username == username).where(cls.removed == False)  # noqa: E712
        )
        return result.scalars().first()

    @classmethod
    async def get_by_api_key(cls, db: AsyncSession, api_key: str) -> Optional["Admin"]:
        result = await db.execute(
            select(cls).where(cls.api_key == api_key).where(cls.removed == False)  # noqa: E712
        )
        return result.scalars().first()

    @classmethod
    async def get_all(
        cls,
        db: AsyncSession,
        *,
        page: Optional[int] = None,
        size: Optional[int] = None,
        roles: Optional[List[AdminRole]] = None,
        availabled: bool = None,
        removed: bool = False,
    ) -> List["Admin"]:
        query = select(cls).where(cls.removed == removed).order_by(cls.created_at.desc())

        if availabled is not None:
            query = query.where(cls.availabled == availabled)
        if page is not None and size is not None:
            if page < 1:
                page = 1
            query = query.offset((page - 1) * size).limit(size)
        if roles is not None:
            query = query.where(cls.role.in_(roles))

        result = await db.execute(query)
        return result.scalars().unique().all()

    @classmethod
    async def create(
        cls,
        db: AsyncSession,
        data: AdminCreate,
    ) -> "Admin":
        admin = cls(
            username=data.username,
            password=cls.generate_hash(data.password),
            role=data.role,
            secret=cls.generate_secret(),
            create_access=data.create_access,
            update_access=data.update_access,
            remove_access=data.remove_access,
            count_limit=data.count_limit,
            usage_limit=data.usage_limit,
            access_prefix=data.access_prefix,
            api_key=cls.generate_api_key(),
            telegram_id=data.telegram_id,
            telegram_token=data.telegram_token,
            telegram_topic_id=data.telegram_topic_id,
            telegram_status=data.telegram_status,
            telegram_send_subscriptions=data.telegram_send_subscriptions,
            telegram_logger_id=data.telegram_logger_id,
            discord_webhook_status=data.discord_webhook_status,
            discord_webhook_url=data.discord_webhook_url,
            discord_send_subscriptions=data.discord_send_subscriptions,
            username_tag=data.username_tag,
            expire_warning_days=data.expire_warning_days,
            usage_warning_percent=data.usage_warning_percent,
            support_url=data.support_url,
            update_interval=data.update_interval,
            announce=data.announce,
            announce_url=data.announce_url,
            access_tag=data.access_tag,
            config_rename=data.config_rename,
        )
        db.add(admin)
        if data.service_ids:
            result = await db.execute(select(Service).where(Service.id.in_(data.service_ids)))
            services = result.scalars().unique().all()
            admin.services.extend(services)
        await db.flush()
        await db.refresh(admin)
        return admin

    @classmethod
    async def enable(cls, db: AsyncSession, admin: "Admin") -> "Admin":
        admin = await db.merge(admin)
        admin.enabled = True
        await db.flush()
        return admin

    @classmethod
    async def disable(cls, db: AsyncSession, admin: "Admin") -> "Admin":
        admin = await db.merge(admin)
        admin.enabled = False
        await db.flush()
        return admin

    @classmethod
    async def update(
        cls,
        db: AsyncSession,
        admin: "Admin",
        data: AdminUpdate,
    ) -> "Admin":
        if data.password is not None:
            admin.password = cls.generate_hash(data.password)
            admin.last_password_reset_at = datetime.utcnow()
        if data.service_ids is not None:
            result = await db.execute(select(Service).where(Service.id.in_(data.service_ids)))
            services = result.scalars().unique().all()
            admin.services = services
        if data.create_access is not None:
            admin.create_access = data.create_access
        if data.update_access is not None:
            admin.update_access = data.update_access
        if data.remove_access is not None:
            admin.remove_access = data.remove_access
        if data.count_limit is not None:
            admin.count_limit = data.count_limit
        if data.usage_limit is not None:
            admin.usage_limit = data.usage_limit
        if data.placeholders is not None:
            admin.placeholders = [placeholder.dict() for placeholder in data.placeholders]
        if data.max_links is not None:
            admin.max_links = data.max_links
        if data.shuffle_links is not None:
            admin.shuffle_links = data.shuffle_links
        if data.access_prefix is not None:
            admin.access_prefix = data.access_prefix
        if data.access_title is not None:
            admin.access_title = data.access_title
        if data.access_description is not None:
            admin.access_description = data.access_description
        if data.telegram_id is not None:
            admin.telegram_id = data.telegram_id if data.telegram_id else None
        if data.telegram_token is not None:
            admin.telegram_token = data.telegram_token if data.telegram_token else None
        if data.expire_warning_days is not None:
            admin.expire_warning_days = data.expire_warning_days if data.expire_warning_days != 0 else None
        if data.usage_warning_percent is not None:
            admin.usage_warning_percent = data.usage_warning_percent if data.usage_warning_percent != 0 else None
        if data.username_tag is not None:
            admin.username_tag = data.username_tag
        if data.support_url is not None:
            admin.support_url = data.support_url if data.support_url else None
        if data.update_interval is not None:
            admin.update_interval = data.update_interval if data.update_interval != 0 else None
        if data.announce is not None:
            admin.announce = data.announce if data.announce else None
        if data.announce_url is not None:
            admin.announce_url = data.announce_url if data.announce_url else None
        if data.telegram_logger_id is not None:
            admin.telegram_logger_id = data.telegram_logger_id if data.telegram_logger_id else None
        if data.telegram_topic_id is not None:
            admin.telegram_topic_id = data.telegram_topic_id if data.telegram_topic_id else None
        if data.telegram_status is not None:
            admin.telegram_status = data.telegram_status
        if data.telegram_send_subscriptions is not None:
            admin.telegram_send_subscriptions = data.telegram_send_subscriptions
        if data.discord_webhook_status is not None:
            admin.discord_webhook_status = data.discord_webhook_status
        if data.discord_webhook_url is not None:
            admin.discord_webhook_url = data.discord_webhook_url if data.discord_webhook_url else None
        if data.discord_send_subscriptions is not None:
            admin.discord_send_subscriptions = data.discord_send_subscriptions
        if data.totp_status is not None:
            admin.totp_status = data.totp_status
        if data.access_tag is not None:
            admin.access_tag = data.access_tag
        if data.config_rename is not None:
            admin.config_rename = data.config_rename if data.config_rename else None
        await db.flush()
        await db.refresh(admin)
        return admin

    @classmethod
    async def update_current(
        cls,
        db: AsyncSession,
        admin: "Admin",
        data: "AdminCurrentUpdate",
    ) -> "Admin":
        admin = await db.merge(admin)
        if data.password is not None:
            admin.password = cls.generate_hash(data.password)
            admin.last_password_reset_at = datetime.utcnow()
        if data.placeholders is not None:
            admin.placeholders = [placeholder.dict() for placeholder in data.placeholders]
        if data.max_links is not None:
            admin.max_links = data.max_links
        if data.shuffle_links is not None:
            admin.shuffle_links = data.shuffle_links
        if data.access_title is not None:
            admin.access_title = data.access_title
        if data.access_description is not None:
            admin.access_description = data.access_description
        if data.telegram_id is not None:
            admin.telegram_id = data.telegram_id if data.telegram_id else None
        if data.telegram_token is not None:
            admin.telegram_token = data.telegram_token if data.telegram_token else None
        if data.expire_warning_days is not None:
            admin.expire_warning_days = data.expire_warning_days if data.expire_warning_days != 0 else None
        if data.usage_warning_percent is not None:
            admin.usage_warning_percent = data.usage_warning_percent if data.usage_warning_percent != 0 else None
        if data.username_tag is not None:
            admin.username_tag = data.username_tag
        if data.support_url is not None:
            admin.support_url = data.support_url if data.support_url else None
        if data.update_interval is not None:
            admin.update_interval = data.update_interval if data.update_interval != 0 else None
        if data.announce is not None:
            admin.announce = data.announce if data.announce else None
        if data.announce_url is not None:
            admin.announce_url = data.announce_url if data.announce_url else None
        if data.telegram_logger_id is not None:
            admin.telegram_logger_id = data.telegram_logger_id if data.telegram_logger_id else None
        if data.telegram_topic_id is not None:
            admin.telegram_topic_id = data.telegram_topic_id if data.telegram_topic_id else None
        if data.telegram_status is not None:
            admin.telegram_status = data.telegram_status
        if data.telegram_send_subscriptions is not None:
            admin.telegram_send_subscriptions = data.telegram_send_subscriptions
        if data.discord_webhook_status is not None:
            admin.discord_webhook_status = data.discord_webhook_status
        if data.discord_webhook_url is not None:
            admin.discord_webhook_url = data.discord_webhook_url if data.discord_webhook_url else None
        if data.discord_send_subscriptions is not None:
            admin.discord_send_subscriptions = data.discord_send_subscriptions
        if data.totp_status is not None:
            admin.totp_status = data.totp_status
        if data.access_tag is not None:
            admin.access_tag = data.access_tag
        if data.config_rename is not None:
            admin.config_rename = data.config_rename if data.config_rename else None
        await db.flush()
        await db.refresh(admin)
        return admin

    @classmethod
    async def remove(cls, db: AsyncSession, admin: "Admin") -> "Admin":
        admin = await db.merge(admin)
        admin.removed = True
        admin.username = None
        await db.flush()
        return admin

    @classmethod
    async def check_exists(cls, db: AsyncSession, username: str) -> bool:
        result = await db.execute(
            select(cls).where(cls.username == username).where(cls.removed == False)  # noqa: E712
        )
        return result.scalars().first() is not None

    @classmethod
    async def verify_credentials(cls, db: AsyncSession, username: str, password: str) -> Optional["Admin"]:
        result = await db.execute(
            select(cls)
            .where(cls.username == username)
            .where(cls.password == cls.generate_hash(password))
            .where(cls.removed == False)  # noqa: E712
        )
        return result.scalars().first()

    @classmethod
    async def update_last_login(cls, db: AsyncSession, admin: "Admin") -> "Admin":
        admin.last_login_at = datetime.utcnow()
        await db.flush()
        return admin

    @classmethod
    async def update_last_online(cls, admin: "Admin") -> None:
        async with GetDB() as db:
            await db.execute(update(cls).where(cls.id == admin.id).values(last_online_at=datetime.utcnow()))
            await db.commit()

    @classmethod
    async def update_last_backup(cls, db: AsyncSession, admin: "Admin") -> "Admin":
        admin.last_backup_at = datetime.utcnow()
        await db.flush()
        return admin

    @classmethod
    async def revoke_api_key(cls, db: AsyncSession, admin: "Admin") -> "Admin":
        admin = await db.merge(admin)
        admin.api_key = cls.generate_api_key()
        await db.flush()
        return admin

    @classmethod
    def generate_totp_secret(cls) -> str:
        # 160-bit random secret encoded as base32 without padding for authenticator apps
        return base64.b32encode(os.urandom(20)).decode("utf-8").rstrip("=")

    @classmethod
    async def rotate_totp_secret(cls, db: AsyncSession, admin: "Admin") -> "Admin":
        """Generate and store a pending TOTP secret for verification."""
        admin = await db.merge(admin)
        secret = cls.generate_totp_secret()
        admin.totp_secret_pending = secret
        await db.flush()
        await db.refresh(admin)
        return admin

    @classmethod
    async def activate_totp_pending(cls, db: AsyncSession, admin: "Admin") -> "Admin":
        """Verify pending TOTP code and activate it."""
        admin = await db.merge(admin)
        if not admin.totp_secret_pending:
            return False
        admin.totp_secret = admin.totp_secret_pending
        admin.totp_secret_pending = None
        admin.totp_status = True
        admin.last_totp_revoked_at = datetime.utcnow()
        await db.flush()
        await db.refresh(admin)
        return admin

    @classmethod
    async def sync_current_counts(cls, db: AsyncSession) -> None:
        """Synchronize current_count for all admins."""
        from sqlalchemy import update, func
        from .subscription import Subscription

        await db.execute(
            update(Admin).values(
                current_count=select(func.count(Subscription.id))
                .where(Subscription.owner_id == Admin.id)
                .where(Subscription.removed == False)
                .scalar_subquery()
            )
        )
        await db.flush()
