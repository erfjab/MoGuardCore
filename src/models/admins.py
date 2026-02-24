import re
from enum import StrEnum
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, validator


class AdminPlaceHolderCategory(StrEnum):
    INFO = "info"
    LIMITED = "limited"
    EXPIRED = "expired"
    DISABLED = "disabled"


ADMIN_FORMATS = [
    "id",
    "username",
    "owner_username",
    "enabled",
    "activated",
    "limited",
    "expired",
    "is_active",
    "limit_usage",
    "current_usage",
    "left_usage",
    "expire_date",
    "expire_in",
    "expire_in_days",
]

ADMIN_CONFIG_FORMATS = ADMIN_FORMATS + [
    "server_id",
    "server_emoji",
    "server_name",
    "server_usage",
]


class AdminPlaceHolder(BaseModel):
    remark: str
    uuid: Optional[str] = None
    address: Optional[str] = None
    port: Optional[int] = None
    categories: list[AdminPlaceHolderCategory]

    @validator("port")
    def validate_port(cls, v):
        if v is not None and (v < 1 or v > 65535):
            raise ValueError("Port must be between 1 and 65535")
        return v

    @validator("remark", "uuid", "address")
    def validate_remark(cls, v):
        if not v or len(v) > 200:
            raise ValueError("Remark, UUID, and Address must be non-empty and at most 200 characters")
        formats = re.findall(r"\{(.*?)\}", v)
        for fmt in formats:
            if fmt not in ADMIN_FORMATS:
                raise ValueError(f"Invalid format '{fmt}' in remark, uuid, or address")
        return v


class AdminRole(StrEnum):
    OWNER = "owner"
    SELLER = "seller"
    RESELLER = "reseller"


class AdminToken(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminResponse(BaseModel):
    id: int
    enabled: bool
    username: str
    role: AdminRole
    service_ids: list[int]
    create_access: Optional[bool]
    update_access: Optional[bool]
    remove_access: Optional[bool]
    count_limit: Optional[int]
    current_count: Optional[int]
    left_count: Optional[int]
    reached_count_limit: Optional[bool]
    usage_limit: Optional[int]
    current_usage: Optional[int]
    left_usage: Optional[int]
    reached_usage_limit: Optional[bool]
    placeholders: Optional[list[AdminPlaceHolder]]
    max_links: Optional[int]
    shuffle_links: Optional[bool]
    config_rename: Optional[str] = None
    api_key: str
    totp_status: Optional[bool]
    access_title: Optional[str] = None
    access_prefix: Optional[str] = None
    access_description: Optional[str] = None
    access_tag: str = "guards"
    telegram_id: Optional[str]
    telegram_token: Optional[str]
    telegram_logger_id: Optional[str]
    telegram_topic_id: Optional[str]
    telegram_status: Optional[bool]
    telegram_send_subscriptions: Optional[bool]
    discord_webhook_status: Optional[bool]
    discord_webhook_url: Optional[str]
    discord_send_subscriptions: Optional[bool] = None
    expire_warning_days: Optional[int]
    usage_warning_percent: Optional[int]
    username_tag: Optional[bool] = None
    support_url: Optional[str] = None
    update_interval: Optional[int] = None
    announce: Optional[str] = None
    announce_url: Optional[str] = None
    last_login_at: Optional[datetime]
    last_online_at: Optional[datetime]
    last_backup_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AdminCreate(BaseModel):
    username: str
    password: str
    role: AdminRole
    service_ids: Optional[list[int]]
    create_access: Optional[bool] = False
    update_access: Optional[bool] = False
    remove_access: Optional[bool] = False
    count_limit: Optional[int] = 300
    usage_limit: Optional[int] = None
    access_prefix: Optional[str] = None
    placeholders: Optional[list[AdminPlaceHolder]] = None
    max_links: Optional[int] = None
    shuffle_links: Optional[bool] = None
    access_title: Optional[str] = None
    access_description: Optional[str] = None
    access_tag: Optional[str] = "guards"
    telegram_id: Optional[str] = None
    telegram_token: Optional[str] = None
    telegram_logger_id: Optional[str] = None
    telegram_topic_id: Optional[str] = None
    telegram_status: Optional[bool] = False
    telegram_send_subscriptions: Optional[bool] = False
    discord_webhook_status: Optional[bool] = False
    discord_webhook_url: Optional[str] = None
    discord_send_subscriptions: Optional[bool] = False
    expire_warning_days: Optional[int] = None
    usage_warning_percent: Optional[int] = None
    username_tag: Optional[bool] = None
    support_url: Optional[str] = None
    update_interval: Optional[int] = None
    announce: Optional[str] = None
    announce_url: Optional[str] = None
    config_rename: Optional[str] = None

    @validator("username")
    def validate_username_and_password(cls, v):
        if not re.match(r"^[a-zA-Z0-9]{3,30}$", v):
            raise ValueError("Invalid username, only allow letters and numbers, length 3-30")
        return v

    @validator("password")
    def validate_password(cls, v):
        if v is not None and not re.match(r"^[a-zA-Z0-9@#&]{3,30}$", v):
            raise ValueError("Invalid password, only allow letters, numbers, and @#&, length 3-30")
        return v

    @validator("role")
    def validate_role(cls, v):
        if v is AdminRole.OWNER:
            raise ValueError("Cannot create owner role")
        return v

    @validator("expire_warning_days")
    def validate_expire_warning_days(cls, v):
        if v is not None and v < 0:
            raise ValueError("expire_warning_days must be non-negative")
        return v

    @validator("usage_warning_percent")
    def validate_usage_warning_percent(cls, v):
        if v is not None and (v < 0 or v > 100):
            raise ValueError("usage_warning_percent must be between 0 and 100")
        return v

    @validator("update_interval")
    def validate_update_interval(cls, v):
        if v is not None and v < 1:
            raise ValueError("update_interval must be at least 1")
        return v

    @validator("access_title", "access_description", "announce")
    def validate_access_title_and_description(cls, v):
        if v is None:
            return v
        if len(v) > 200:
            raise ValueError("Access title and description and announce must be at most 200 characters")
        formats = re.findall(r"\{(.*?)\}", v)
        for fmt in formats:
            if fmt not in ADMIN_FORMATS:
                raise ValueError(f"Invalid format '{fmt}' in access title or description or announce")
        return v

    @validator("config_rename")
    def validate_config_rename(cls, v):
        if v is None:
            return v
        if len(v) > 200:
            raise ValueError("Config rename must be at most 200 characters")
        formats = re.findall(r"\{(.*?)\}", v)
        for fmt in formats:
            if fmt not in ADMIN_CONFIG_FORMATS:
                raise ValueError(f"Invalid format '{fmt}' in config rename")
        return v

    @validator("max_links")
    def validate_max_links(cls, v):
        if v is not None and v < 0:
            raise ValueError("max_links must be non-negative")
        return v

    @validator("access_tag")
    def validate_access_tag(cls, v):
        if not re.match(r"^[a-zA-Z0-9]{4,30}$", v):
            raise ValueError("Invalid access_tag, only allow letters and numbers, length 4-30")
        return v


class AdminUpdate(BaseModel):
    password: Optional[str] = None
    create_access: Optional[bool] = None
    update_access: Optional[bool] = None
    remove_access: Optional[bool] = None
    count_limit: Optional[int] = None
    usage_limit: Optional[int] = None
    service_ids: Optional[list[int]] = None
    placeholders: Optional[list[AdminPlaceHolder]] = None
    max_links: Optional[int] = None
    shuffle_links: Optional[bool] = None
    config_rename: Optional[str] = None
    access_prefix: Optional[str] = None
    access_title: Optional[str] = None
    access_description: Optional[str] = None
    access_tag: Optional[str] = None
    telegram_id: Optional[str] = None
    telegram_token: Optional[str] = None
    telegram_topic_id: Optional[str] = None
    telegram_logger_id: Optional[str] = None
    telegram_status: Optional[bool] = None
    telegram_send_subscriptions: Optional[bool] = None
    discord_webhook_status: Optional[bool] = None
    discord_webhook_url: Optional[str] = None
    discord_send_subscriptions: Optional[bool] = None
    expire_warning_days: Optional[int] = None
    announce: Optional[str] = None
    announce_url: Optional[str] = None
    usage_warning_percent: Optional[int] = None
    username_tag: Optional[bool] = None
    support_url: Optional[str] = None
    update_interval: Optional[int] = None
    totp_status: Optional[bool] = None

    @validator("access_title", "access_description", "announce")
    def validate_access_title_and_description(cls, v):
        if v is None:
            return v
        if len(v) > 200:
            raise ValueError("Access title and description and announce must be at most 200 characters")
        formats = re.findall(r"\{(.*?)\}", v)
        for fmt in formats:
            if fmt not in ADMIN_FORMATS:
                raise ValueError(f"Invalid format '{fmt}' in access title or description or announce")
        return v

    @validator("config_rename")
    def validate_config_rename(cls, v):
        if v is None:
            return v
        if len(v) > 200:
            raise ValueError("Config rename must be at most 200 characters")
        formats = re.findall(r"\{(.*?)\}", v)
        for fmt in formats:
            if fmt not in ADMIN_CONFIG_FORMATS:
                raise ValueError(f"Invalid format '{fmt}' in config rename")
        return v

    @validator("password")
    def validate_password(cls, v):
        if v is not None and not re.match(r"^[a-zA-Z0-9@#&]{3,30}$", v):
            raise ValueError("Invalid password, only allow letters, numbers, and @#&, length 3-30")
        return v

    @validator("max_links")
    def validate_max_links(cls, v):
        if v is not None and v < 0:
            raise ValueError("max_links must be non-negative")
        return v

    @validator("usage_warning_percent")
    def validate_usage_warning_percent(cls, v):
        if v is not None and (v < 0 or v > 100):
            raise ValueError("usage_warning_percent must be between 0 and 100")
        return v

    @validator("expire_warning_days")
    def validate_expire_warning_days(cls, v):
        if v is not None and v < 0:
            raise ValueError("expire_warning_days must be non-negative")
        return v

    @validator("update_interval")
    def validate_update_interval(cls, v):
        if v is not None and v < 1:
            raise ValueError("update_interval must be at least 1")
        return v

    @validator("access_tag")
    def validate_access_tag(cls, v):
        if v is not None and not re.match(r"^[a-zA-Z0-9]{4,30}$", v):
            raise ValueError("Invalid access_tag, only allow letters and numbers, length 4-30")
        return v


class AdminCurrentUpdate(BaseModel):
    password: Optional[str] = None
    placeholders: Optional[list[AdminPlaceHolder]] = None
    max_links: Optional[int] = None
    shuffle_links: Optional[bool] = None
    access_title: Optional[str] = None
    access_description: Optional[str] = None
    access_tag: Optional[str] = None
    config_rename: Optional[str] = None
    telegram_id: Optional[str] = None
    telegram_token: Optional[str] = None
    telegram_topic_id: Optional[str] = None
    telegram_status: Optional[bool] = None
    telegram_send_subscriptions: Optional[bool] = None
    telegram_logger_id: Optional[str] = None
    discord_webhook_status: Optional[bool] = None
    discord_webhook_url: Optional[str] = None
    discord_send_subscriptions: Optional[bool] = None
    expire_warning_days: Optional[int] = None
    usage_warning_percent: Optional[int] = None
    username_tag: Optional[bool] = None
    support_url: Optional[str] = None
    update_interval: Optional[int] = None
    announce: Optional[str] = None
    announce_url: Optional[str] = None
    totp_status: Optional[bool] = None

    @validator("access_title", "access_description", "announce")
    def validate_access_title_and_description(cls, v):
        if v is None:
            return v
        if len(v) > 200:
            raise ValueError("Access title and description and announce must be at most 200 characters")
        formats = re.findall(r"\{(.*?)\}", v)
        for fmt in formats:
            if fmt not in ADMIN_FORMATS:
                raise ValueError(f"Invalid format '{fmt}' in access title or description or announce")
        return v

    @validator("config_rename")
    def validate_config_rename(cls, v):
        if v is None:
            return v
        if len(v) > 200:
            raise ValueError("Config rename must be at most 200 characters")
        formats = re.findall(r"\{(.*?)\}", v)
        for fmt in formats:
            if fmt not in ADMIN_CONFIG_FORMATS:
                raise ValueError(f"Invalid format '{fmt}' in config rename")
        return v

    @validator("password")
    def validate_password(cls, v):
        if v is not None and not re.match(r"^[a-zA-Z0-9@#&]{3,30}$", v):
            raise ValueError("Invalid password, only allow letters, numbers, and @#&, length 3-30")
        return v

    @validator("max_links")
    def validate_max_links(cls, v):
        if v is not None and v < 0:
            raise ValueError("max_links must be non-negative")
        return v

    @validator("usage_warning_percent")
    def validate_usage_warning_percent(cls, v):
        if v is not None and (v < 0 or v > 100):
            raise ValueError("usage_warning_percent must be between 0 and 100")
        return v

    @validator("expire_warning_days")
    def validate_expire_warning_days(cls, v):
        if v is not None and v < 0:
            raise ValueError("expire_warning_days must be non-negative")
        return v

    @validator("update_interval")
    def validate_update_interval(cls, v):
        if v is not None and v < 1:
            raise ValueError("update_interval must be at least 1")
        return v

    @validator("access_tag")
    def validate_access_tag(cls, v):
        if v is not None and not re.match(r"^[a-zA-Z0-9]{4,30}$", v):
            raise ValueError("Invalid access_tag, only allow letters and numbers, length 4-30")
        return v


class AdminUsageLog(BaseModel):
    usage: int
    created_at: datetime


class AdminUsageLogsResponse(BaseModel):
    admin: AdminResponse
    usages: list[AdminUsageLog]
