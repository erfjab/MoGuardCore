import re
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, validator


class AutoRenewalResponse(BaseModel):
    id: int
    limit_expire: Optional[int]
    limit_usage: Optional[int]
    reset_usage: bool

    class Config:
        from_attributes = True


class AutoRenewalCreate(BaseModel):
    limit_expire: int
    limit_usage: int
    reset_usage: bool = False

    @validator("limit_usage")
    def validate_limit_usage(cls, v):
        if v is not None and v < 0:
            raise ValueError("Limit usage must be 0 or greater")
        return v


class AutoRenewalUpdate(BaseModel):
    id: int
    limit_expire: Optional[int] = None
    limit_usage: Optional[int] = None
    reset_usage: Optional[bool] = None

    @validator("limit_usage")
    def validate_limit_usage(cls, v):
        if v is not None and v < 0:
            raise ValueError("Limit usage must be 0 or greater")
        return v


class SubscriptionResponse(BaseModel):
    id: int
    username: str
    owner_username: str
    access_key: str

    enabled: bool
    activated: bool
    reached: bool
    limited: bool
    expired: bool
    is_active: bool
    is_online: bool

    link: str

    limit_usage: int
    reset_usage: int
    total_usage: int
    current_usage: int
    limit_expire: int
    auto_delete_days: int

    service_ids: list[int]
    note: Optional[str]
    telegram_id: Optional[str]
    discord_webhook_url: Optional[str]

    online_at: Optional[datetime]
    last_reset_at: Optional[datetime]
    last_revoke_at: Optional[datetime]
    last_request_at: Optional[datetime]
    last_client_agent: Optional[str]
    created_at: datetime
    updated_at: datetime

    auto_renewals: List[AutoRenewalResponse] = []

    class Config:
        from_attributes = True


class SubscriptionCreate(BaseModel):
    username: str
    limit_usage: int
    limit_expire: int
    service_ids: list[int]
    access_key: Optional[str] = None
    note: Optional[str] = None
    telegram_id: Optional[str] = None
    discord_webhook_url: Optional[str] = None
    auto_delete_days: Optional[int] = None
    auto_renewals: Optional[List[AutoRenewalCreate]] = []

    @validator("access_key")
    def validate_access_key(cls, v):
        if v and len(v) != 32:
            raise ValueError("Access key must be 32 characters long")
        return v

    @validator("note")
    def validate_note(cls, v):
        if v is None:
            return v
        if len(v) > 1024:
            raise ValueError("Note must be at most 1024 characters")
        return v

    @validator("username")
    def validate_username(cls, v):
        if not re.match(r"^[a-z0-9_]{3,30}$", v):
            raise ValueError("Invalid username, only allow letters and numbers, length 3-30")
        return v

    @validator("limit_usage")
    def validate_limit_usage(cls, v):
        if v < 0:
            raise ValueError("Limit usage must be at least 0")
        # if v != 0 and v < 21474836480:
        #     raise ValueError("Limit usage must be at least 21474836480 bytes (20 GB) or 0 for unlimited")
        return v

    @validator("limit_expire")
    def validate_limit_expire(cls, v):
        now_ts = int(datetime.utcnow().timestamp())
        max_years_seconds = 315360000  # 10 years

        if v > 0:
            if v <= now_ts:
                raise ValueError("Limit expire must be a valid unix timestamp in the future")
            if v > now_ts + max_years_seconds:
                raise ValueError("Limit expire cannot be more than 10 years in the future")
        elif v < 0:
            if abs(v) > max_years_seconds:
                raise ValueError("Limit expire duration cannot be more than 10 years")
        return v

    @validator("auto_delete_days")
    def validate_auto_delete_days(cls, v):
        if v < 0:
            raise ValueError("Auto delete days must be 0 or greater")
        if v > 999:
            raise ValueError("Auto delete days must be less than or equal to 999")
        return v


class SubscriptionUpdate(BaseModel):
    username: Optional[str] = None
    limit_usage: Optional[int] = None
    limit_expire: Optional[int] = None
    service_ids: Optional[list[int]] = None
    note: Optional[str] = None
    telegram_id: Optional[str] = None
    discord_webhook_url: Optional[str] = None
    auto_delete_days: Optional[int] = None
    auto_renewals: Optional[List[AutoRenewalUpdate]] = None

    @validator("username")
    def validate_username(cls, v):
        if not re.match(r"^[a-z0-9_]{3,30}$", v):
            raise ValueError("Invalid username, only allow letters and numbers, length 3-30")
        return v

    @validator("note")
    def validate_note(cls, v):
        if v is None:
            return v
        if len(v) > 1024:
            raise ValueError("Note must be at most 1024 characters")
        return v

    @validator("limit_usage")
    def validate_limit_usage(cls, v):
        if not v:
            return v
        if v < 0:
            raise ValueError("Limit usage must be at least 0")
        # if v != 0 and v < 21474836480:
        #     raise ValueError("Limit usage must be at least 21474836480 bytes (20 GB) or 0 for unlimited")
        return v

    @validator("limit_expire")
    def validate_limit_expire(cls, v):
        if not v:
            return v
        now_ts = int(datetime.utcnow().timestamp())
        max_years_seconds = 315360000  # 10 years

        if v > 0:
            if v <= now_ts:
                raise ValueError("Limit expire must be a valid unix timestamp in the future")
            if v > now_ts + max_years_seconds:
                raise ValueError("Limit expire cannot be more than 10 years in the future")
        elif v < 0:
            if abs(v) > max_years_seconds:
                raise ValueError("Limit expire duration cannot be more than 10 years")
        return v

    @validator("auto_delete_days")
    def validate_auto_delete_days(cls, v):
        if v is None:
            return v
        if v < 0:
            raise ValueError("Auto delete days must be 0 or greater")
        if v > 999:
            raise ValueError("Auto delete days must be less than or equal to 999")
        return v


class SubscriptionUsageLog(BaseModel):
    usage: int
    created_at: datetime


class SubscriptionUsageLogsResponse(BaseModel):
    subscription: SubscriptionResponse
    usages: list[SubscriptionUsageLog]


class SubscriptionStatsResponse(BaseModel):
    total: int
    active: int
    inactive: int
    disabled: int
    expired: int
    limited: int
    has_revoked: int
    has_reseted: int
    total_removed: int
    total_usage: int
